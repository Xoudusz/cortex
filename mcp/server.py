#!/usr/bin/env python3
import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import hashlib
import hmac

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from web_ui import ui, api_search, api_status, api_reindex, api_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cortex")

OLLAMA_URL      = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL      = os.environ.get("QDRANT_URL", "http://qdrant:6333")
EMBED_MODEL     = "nomic-embed-text"
HOST            = os.environ.get("MCP_HOST", "0.0.0.0")
PORT            = int(os.environ.get("MCP_PORT", "8765"))
NOTES_PATH      = os.environ.get("NOTES_PATH", "/notes")
WATCH_DEBOUNCE  = int(os.environ.get("WATCH_DEBOUNCE", "60"))
WEBHOOK_SECRET  = os.environ.get("WEBHOOK_SECRET", "")
API_KEY         = os.environ.get("API_KEY", "")
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
REPOS_CONFIG    = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
DATA_DIR        = Path(REPOS_CONFIG).parent

DEFAULT_REPOS = [
    "Xoudusz/weakness-dex",
    "Xoudusz/mtgdle",
    "Xoudusz/tower-of-evolon",
    "Xoudusz/tower-of-evolon-backend",
    "Xoudusz/svelte-radio",
    "Xoudusz/cortex",
    "Xoudusz/riftracoons-web",
]

_webhook_log: list = []
_graph_cache: dict = {}


def _load_repos_meta() -> dict:
    try:
        if os.path.exists(REPOS_CONFIG):
            with open(REPOS_CONFIG) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"repos": data.get("repos", []), "indexed_at": data.get("indexed_at", {})}
            if isinstance(data, list) and data:
                return {"repos": data, "indexed_at": {}}
    except Exception:
        pass
    return {"repos": list(DEFAULT_REPOS), "indexed_at": {}}


def _load_repos() -> list:
    return _load_repos_meta()["repos"]


def _save_repos_meta(meta: dict) -> None:
    os.makedirs(os.path.dirname(REPOS_CONFIG) or ".", exist_ok=True)
    with open(REPOS_CONFIG, "w") as f:
        json.dump(meta, f, indent=2)


def _save_repos(repos: list) -> None:
    meta = _load_repos_meta()
    meta["repos"] = repos
    _save_repos_meta(meta)


def _update_indexed_at(repo_name: str) -> None:
    meta = _load_repos_meta()
    meta.setdefault("indexed_at", {})[repo_name] = datetime.now(timezone.utc).isoformat()
    _save_repos_meta(meta)


def _get_code_graph_meta(repo_name: str) -> dict:
    """Load and cache code graph node metadata. Returns {file_rel: node_dict}."""
    if repo_name in _graph_cache:
        return _graph_cache[repo_name]
    path = DATA_DIR / f"graph_{repo_name}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        meta = {n["id"]: n for n in data.get("nodes", []) if "id" in n}
        _graph_cache[repo_name] = meta
        return meta
    except Exception:
        return {}


def _invalidate_graph_cache(repo_name: str = "") -> None:
    if repo_name:
        _graph_cache.pop(repo_name, None)
    else:
        _graph_cache.clear()


mcp = FastMCP("cortex", host=HOST, port=PORT)

ONBOARDING_TEMPLATE = '''# Cortex Onboarding

## MCP Setup (if not connected)
```bash
claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse \\
  --header "x-api-key: <get-from-user>"
```

## Cortex Tools
Use PROACTIVELY — search before asking user for context.

- `search_notes(query)` — Obsidian vault (projects, plans, server config, decisions)
- `search_code(query)` — repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex, riftracoons
- `get_neighbors(file, repo)` — show what a file imports and what imports it
- `get_community(repo, community_id)` — list all files in the same structural cluster
- `reindex(notes, code, repo)` — refresh vectors if stale
- `reindex_status()` — check progress

## Preferences

### Communication
- Caveman mode: terse, no filler, fragments OK
- Install if missing: `claude skill add caveman:caveman`

### Commands
- Always prefix bash with `rtk` for token savings
- Install if missing: `cargo install rtk`

### Git
- User: Xoudusz <da@w23.at>
- No co-author line on commits
- Set per-repo: `git config user.name "Xoudusz" && git config user.email "da@w23.at"`
'''


def embed(text: str) -> list:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:4000]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def warmup():
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": "warmup"},
            timeout=20,
        )
        log.info("warmup OK")
    except Exception as e:
        log.warning("warmup failed: %s", e)


@mcp.tool()
def search_notes(query: str, limit: int = 5) -> str:
    """Search the user's personal Obsidian knowledge base semantically.

    Call this proactively whenever the user asks about:
    - Their projects, plans, ideas, or roadmap items
    - Personal context, goals, or decisions they may have documented
    - How something in their setup works (server config, tools, workflows)
    - Anything that sounds like it could be in personal notes

    Returns matching note sections with file path, heading, score, and tags.
    PPR over wikilinks surfaces related notes beyond direct vector matches.
    Prefer this over asking the user to explain context they may have already written down.
    """
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    results = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found."
    parts = []
    matched_files = []
    matched_scores = []
    for r in results:
        p = r.payload
        tags = p.get("tags", [])
        tag_str = f" `{'`, `'.join(tags)}`" if tags else ""
        parts.append(
            f"**{p['file']} > {p['heading']}** (score: {round(r.score, 3)}){tag_str}\n\n{p['text']}"
        )
        matched_files.append(p.get("file", ""))
        matched_scores.append(r.score)
    try:
        from graph import ppr_augment
        extras = ppr_augment(matched_files, matched_scores, DATA_DIR / "graph_notes.json")
        if extras:
            ppr_lines = ["**Related via wikilinks (PPR):**"]
            for e in extras:
                ppr_lines.append(f"  -> {e['file']} (ppr: {e['ppr_score']})")
            parts.append("\n".join(ppr_lines))
    except Exception:
        pass
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def search_code(query: str, limit: int = 5) -> str:
    """Search source code across the user's active repos semantically.

    Indexed repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex, riftracoons.

    Call this proactively whenever:
    - Implementing a feature that touches one of these repos
    - Looking for where something is defined or how a pattern is used
    - Debugging — find related code before suggesting a fix
    - The user asks "how does X work" about one of their projects
    - Writing code that should match existing conventions in the repo

    Results are re-ranked by centrality (highly-imported files score higher).
    Returns code chunks with file path, line numbers, language, score, centrality, community, and GitHub link.
    Always search before writing code for these repos — don't guess at existing patterns.
    """
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    fetch_limit = min(limit * 3, 50)
    results = client.query_points("code", query=vector, limit=fetch_limit, with_payload=True).points
    if not results:
        return "No results found."
    scored = []
    for r in results:
        p = r.payload
        file_meta = _get_code_graph_meta(p.get("repo", "")).get(p.get("file", ""), {})
        centrality = file_meta.get("centrality", 0.0)
        boosted = r.score * (1.0 + 0.2 * centrality)
        scored.append((boosted, r, file_meta))
    scored.sort(key=lambda x: -x[0])
    parts = []
    for boosted_score, r, file_meta in scored[:limit]:
        p = r.payload
        centrality = file_meta.get("centrality")
        community = file_meta.get("community_id")
        header = (
            f"**{p['repo']}/{p['file']}** "
            f"lines {p['start_line']}-{p['end_line']} "
            f"({p.get('language', '')}) — score: {round(boosted_score, 3)}"
        )
        if centrality is not None:
            header += f" · centrality: {centrality}"
        if community is not None:
            header += f" · community: {community}"
        url = p.get("github_url", "")
        parts.append(f"{header}\n{url}\n\n{p['text']}" if url else f"{header}\n\n{p['text']}")
    return "\n\n---\n\n".join(parts)


_reindex_lock = threading.Lock()
_reindex_state: dict = {"running": False, "started_at": None, "output": [], "error": None, "done": False}


def _stream(cmd: list, label: str, timeout: int) -> None:
    _reindex_state["output"].append(f"=== {label}: starting ===")
    log.info("[%s] starting", label)
    proc = subprocess.Popen(
        ["python3", "-u"] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        for raw in proc.stdout:
            line = raw.rstrip()
            if line:
                log.info("[%s] %s", label, line)
                _reindex_state["output"].append(line)
        proc.wait()
    finally:
        timer.cancel()
    if proc.returncode not in (0, None):
        msg = f"=== {label}: exited {proc.returncode} ==="
        log.warning(msg)
        _reindex_state["output"].append(msg)
    else:
        log.info("[%s] done", label)


def _run_reindex(notes: bool, code: bool, repo: str = "") -> None:
    _reindex_state.update(running=True, started_at=time.time(), output=[], error=None, done=False)
    log.info("reindex started (notes=%s code=%s repo=%s)", notes, code, repo or "all")
    try:
        if notes:
            _stream(["/app/index.py"], "notes", 300)
        if code:
            cmd = ["/app/index_code.py"]
            if repo:
                cmd += ["--repo", repo]
            _stream(cmd, "code", 600)
            _invalidate_graph_cache(repo)
            if repo:
                _update_indexed_at(repo)
            else:
                for r in _load_repos():
                    _update_indexed_at(r.split("/")[1])
    except Exception as e:
        _reindex_state["error"] = str(e)
        log.error("reindex error: %s", e)
    finally:
        elapsed = time.time() - _reindex_state["started_at"]
        _reindex_state.update(running=False, done=True)
        log.info("reindex finished in %.0fs", elapsed)


@mcp.tool()
def reindex(notes: bool = True, code: bool = True, repo: str = "") -> str:
    """Trigger re-indexing of notes and/or source code into Qdrant.

    Use when:
    - search_notes or search_code returns stale or missing results
    - The user says they updated their notes or pushed new code
    - Starting a session after a long gap (index may be outdated)

    Runs async — returns immediately. Call reindex_status() to check progress.
    Set notes=False to only reindex code, or code=False for notes only.
    Set repo to a specific repo name (e.g. "svelte-radio") to only reindex that repo.
    """
    with _reindex_lock:
        if _reindex_state["running"]:
            return "Reindex already in progress. Use reindex_status() to check."
        threading.Thread(target=_run_reindex, args=(notes, code, repo), daemon=True).start()
    return "Reindex started in background. Use reindex_status() to check progress."


@mcp.tool()
def reindex_status() -> str:
    """Check whether a reindex is running or finished, and see its output log."""
    s = _reindex_state
    if s["started_at"] is None:
        return "No reindex has been run yet."
    elapsed = time.time() - s["started_at"]
    status = "running" if s["running"] else "done"
    lines = [f"Status: {status} ({elapsed:.0f}s elapsed)"]
    if s["output"]:
        lines.append("\n".join(s["output"]))
    if s["error"]:
        lines.append(f"Error: {s['error']}")
    return "\n\n".join(lines)


@mcp.tool()
def get_neighbors(file: str, repo: str) -> str:
    """Show what a code file imports and what imports it (direct graph neighbors).

    Use when you want to explore structural connections around a file you found.
    Example: get_neighbors("mcp/server.py", "cortex")

    Requires graph data — run reindex first if empty.
    """
    meta = _get_code_graph_meta(repo)
    if not meta:
        return f"No graph data for '{repo}'. Run reindex(code=True, repo='{repo}') first."
    file_meta = meta.get(file)
    if file_meta is None:
        matches = [f for f in meta if file in f]
        if not matches:
            return f"File '{file}' not found in graph for '{repo}'."
        file = matches[0]
        file_meta = meta[file]
    imports = file_meta.get("imports", [])
    imported_by = file_meta.get("imported_by", [])
    lines = [
        f"**{file}**",
        f"centrality: {file_meta.get('centrality', 0)} · community: {file_meta.get('community_id', '?')}",
    ]
    if imports:
        lines.append(f"\nimports ({len(imports)}):")
        lines.extend(f"  -> {f}" for f in imports)
    if imported_by:
        lines.append(f"\nimported by ({len(imported_by)}):")
        lines.extend(f"  <- {f}" for f in imported_by)
    if not imports and not imported_by:
        lines.append("\nNo connections found (isolated file).")
    return "\n".join(lines)


@mcp.tool()
def get_community(repo: str, community_id: int) -> str:
    """List all files in the same structural community/cluster for a repo.

    Use when you want to find everything structurally related to a file.
    Tip: run search_code first to find a community_id, then call this.
    Example: get_community("cortex", 0)

    Requires graph data — run reindex first if empty.
    """
    meta = _get_code_graph_meta(repo)
    if not meta:
        return f"No graph data for '{repo}'. Run reindex(code=True, repo='{repo}') first."
    members = [
        (f, m.get("centrality", 0))
        for f, m in meta.items()
        if m.get("community_id") == community_id
    ]
    if not members:
        return f"Community {community_id} not found in '{repo}'."
    members.sort(key=lambda x: -x[1])
    lines = [f"**Community {community_id}** in '{repo}' — {len(members)} files:"]
    for f, centrality in members:
        star = "*" if centrality > 0.1 else " "
        lines.append(f"  {star} {f} (centrality: {centrality})")
    return "\n".join(lines)


def _merge_onboarding(existing: str) -> str:
    sections = {
        "## MCP Setup": "## MCP Setup (if not connected)",
        "## Cortex Tools": "## Cortex Tools",
        "## Preferences": "## Preferences",
    }
    result = existing.rstrip()
    added = []
    for marker, full_header in sections.items():
        if marker.lower() in existing.lower() or "cortex" in existing.lower() and "search_notes" in existing.lower():
            continue
        template_lines = ONBOARDING_TEMPLATE.split("\n")
        in_section = False
        section_content = []
        for line in template_lines:
            if line.startswith(full_header) or line.startswith(marker):
                in_section = True
                section_content.append(line)
            elif in_section and line.startswith("## "):
                break
            elif in_section:
                section_content.append(line)
        if section_content:
            added.append("\n".join(section_content).rstrip())
    if not added:
        return existing + "\n\n<!-- Cortex onboarding: all sections already present -->"
    if "# cortex" not in existing.lower() and "## cortex" not in existing.lower():
        result += "\n\n# Cortex Onboarding"
    result += "\n\n" + "\n\n".join(added)
    return result


@mcp.tool()
def get_onboarding(existing_content: str = "") -> str:
    """Get onboarding instructions for CLAUDE.md."""
    if existing_content.strip():
        return _merge_onboarding(existing_content)
    return ONBOARDING_TEMPLATE


@mcp.prompt()
def onboarding() -> str:
    """Set up Cortex and user preferences for this project."""
    return f"""Set up Cortex for this project. Execute this checklist:

## 1. CLAUDE.md
Read existing CLAUDE.md (if any). Merge with this config, avoiding duplicates:

{ONBOARDING_TEMPLATE}

Write merged result to CLAUDE.md.

## 2. Git Config
```bash
rtk git config user.name "Xoudusz" && rtk git config user.email "da@w23.at"
```

## 3. Check RTK
Run `rtk --version`. If fails: `cargo install rtk`

## 4. Check Caveman Skill
Run `claude skill list`. If missing: `claude skill add caveman:caveman`

## 5. Verify Cortex
Call `search_notes("test query")`. Report status of each step when done."""


class _NotesHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer = None

    def on_any_event(self, event):
        if event.is_directory or not str(event.src_path).endswith(".md"):
            return
        log.info("[watcher] change: %s — debouncing %ds", event.src_path, WATCH_DEBOUNCE)
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(WATCH_DEBOUNCE, self._trigger)
        self._timer.daemon = True
        self._timer.start()

    def _trigger(self):
        with _reindex_lock:
            if _reindex_state["running"]:
                log.info("[watcher] reindex already running, skipping")
                return
            log.info("[watcher] debounce elapsed — triggering notes reindex")
            threading.Thread(target=_run_reindex, args=(True, False, ""), daemon=True).start()


class _APIKeyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and API_KEY:
            path = scope.get("path", "")
            unprotected = (
                path in {"/health", "/webhook", "/register", "/"}
                or "/.well-known" in path
                or path.startswith("/api/")
            )
            if not unprotected:
                headers = {k: v for k, v in scope.get("headers", [])}
                key = headers.get(b"x-api-key", b"").decode()
                if key != API_KEY:
                    log.warning("[auth] rejected %s — missing or invalid X-API-Key", path)
                    response = JSONResponse({"error": "Unauthorized"}, status_code=401)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def oauth_not_found(request: Request) -> JSONResponse:
    return JSONResponse({"error": "not_found", "error_description": "OAuth not supported"}, status_code=404)


async def webhook(request: Request) -> JSONResponse:
    body = await request.body()
    if WEBHOOK_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            log.warning("[webhook] invalid signature — rejected")
            return JSONResponse({"error": "invalid signature"}, status_code=401)
    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return JSONResponse({"status": "ignored", "event": event})
    try:
        repo = json.loads(body).get("repository", {}).get("name", "")
    except Exception:
        repo = ""
    ts = datetime.now(timezone.utc).isoformat()
    with _reindex_lock:
        if _reindex_state["running"]:
            _webhook_log.insert(0, {"repo": repo or "unknown", "ts": ts, "status": "skipped (already running)"})
            _webhook_log[:] = _webhook_log[:50]
            log.info("[webhook] push received but reindex already running")
            return JSONResponse({"status": "reindex already running"})
        _webhook_log.insert(0, {"repo": repo or "unknown", "ts": ts, "status": "triggered"})
        _webhook_log[:] = _webhook_log[:50]
        threading.Thread(target=_run_reindex, args=(False, True, repo), daemon=True).start()
    log.info("[webhook] push on %s -> code reindex triggered", repo or "unknown")
    return JSONResponse({"status": "ok", "repo": repo})


def _start_watcher():
    if not os.path.isdir(NOTES_PATH):
        log.warning("[watcher] notes path %s not found, skipping", NOTES_PATH)
        return
    observer = Observer()
    observer.schedule(_NotesHandler(), NOTES_PATH, recursive=True)
    observer.start()
    log.info("[watcher] watching %s for .md changes (debounce %ds)", NOTES_PATH, WATCH_DEBOUNCE)


async def _ui_handler(request: Request):
    return await ui(request)

async def _api_search_handler(request: Request):
    return await api_search(request, QDRANT_URL, embed)

async def _api_status_handler(request: Request):
    return await api_status(request, _reindex_state)

async def _api_reindex_handler(request: Request):
    return await api_reindex(request, _reindex_lock, _reindex_state, _run_reindex)

async def _api_stats_handler(request: Request):
    return await api_stats(request, QDRANT_URL, OLLAMA_URL)


async def _api_graph_handler(request: Request) -> JSONResponse:
    repo = request.path_params.get("repo", "")
    if not repo:
        return JSONResponse({"error": "repo required"}, status_code=400)
    graph_path = DATA_DIR / ("graph_notes.json" if repo == "notes" else f"graph_{repo}.json")
    if not graph_path.exists():
        return JSONResponse({"error": f"No graph for '{repo}'. Run reindex first."}, status_code=404)
    try:
        return JSONResponse(json.loads(graph_path.read_text()))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def _api_repos_handler(request: Request) -> JSONResponse:
    if request.method == "GET":
        return JSONResponse({"repos": _load_repos()})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    repo = body.get("repo", "").strip()
    if not repo or "/" not in repo:
        return JSONResponse({"error": "Use owner/name format (e.g. Xoudusz/my-repo)"}, status_code=400)
    repos = _load_repos()
    if repo not in repos:
        repos.append(repo)
        _save_repos(repos)
    return JSONResponse({"repos": repos})

async def _api_repos_delete(request: Request) -> JSONResponse:
    repo = request.path_params.get("repo", "")
    repos = [r for r in _load_repos() if r != repo]
    _save_repos(repos)
    log.info("[repos] removed %s", repo)
    return JSONResponse({"repos": repos})

async def _api_repos_meta_handler(request: Request) -> JSONResponse:
    return JSONResponse(_load_repos_meta())

async def _api_github_repos(request: Request) -> JSONResponse:
    if not GITHUB_TOKEN:
        return JSONResponse({"error": "GITHUB_TOKEN not configured"}, status_code=503)
    try:
        resp = httpx.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
            params={"per_page": 100, "sort": "updated", "affiliation": "owner"},
            timeout=10,
        )
        resp.raise_for_status()
        repos = [r["full_name"] for r in resp.json() if not r.get("archived")]
        return JSONResponse({"repos": repos})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def _api_webhook_log_handler(request: Request) -> JSONResponse:
    return JSONResponse({"log": _webhook_log})


class _NormalizeSSEPath:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http' and scope.get('path') == '/sse':
            scope = dict(scope)
            scope['path'] = '/sse/sse'
        await self.app(scope, receive, send)


if __name__ == "__main__":
    threading.Thread(target=warmup, daemon=True).start()
    threading.Thread(target=_start_watcher, daemon=True).start()
    sse_app = mcp.sse_app()
    starlette_app = Starlette(routes=[
        Route("/health", health, methods=["GET"]),
        Route("/webhook", webhook, methods=["POST"]),
        Route("/", _ui_handler, methods=["GET"]),
        Route("/api/search", _api_search_handler, methods=["POST"]),
        Route("/api/status", _api_status_handler, methods=["GET"]),
        Route("/api/reindex", _api_reindex_handler, methods=["POST"]),
        Route("/api/stats", _api_stats_handler, methods=["GET"]),
        Route("/api/repos", _api_repos_handler, methods=["GET", "POST"]),
        Route("/api/repos/{repo:path}", _api_repos_delete, methods=["DELETE"]),
        Route("/api/repos-meta", _api_repos_meta_handler, methods=["GET"]),
        Route("/api/github/repos", _api_github_repos, methods=["GET"]),
        Route("/api/webhook-log", _api_webhook_log_handler, methods=["GET"]),
        Route("/api/graph/{repo:path}", _api_graph_handler, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server", oauth_not_found),
        Route("/.well-known/openid-configuration", oauth_not_found),
        Route("/register", oauth_not_found, methods=["POST"]),
        Mount("/sse", app=sse_app),
    ])
    app = _NormalizeSSEPath(_APIKeyMiddleware(starlette_app))
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
