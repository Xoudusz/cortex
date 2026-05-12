#!/usr/bin/env python3
import json
import logging
import os
import subprocess
import threading
import time

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
- `search_code(query)` — repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex
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


def embed(text: str) -> list[float]:
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
    Prefer this over asking the user to explain context they may have already written down.
    """
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    results = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found."
    parts = []
    for r in results:
        p = r.payload
        tags = p.get("tags", [])
        tag_str = f" `{'`, `'.join(tags)}`" if tags else ""
        parts.append(
            f"**{p['file']} › {p['heading']}** (score: {round(r.score, 3)}){tag_str}\n\n{p['text']}"
        )
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def search_code(query: str, limit: int = 5) -> str:
    """Search source code across the user's active repos semantically.

    Indexed repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex.

    Call this proactively whenever:
    - Implementing a feature that touches one of these repos
    - Looking for where something is defined or how a pattern is used
    - Debugging — find related code before suggesting a fix
    - The user asks "how does X work" about one of their projects
    - Writing code that should match existing conventions in the repo

    Returns code chunks with file path, line numbers, language, score, and GitHub link.
    Always search before writing code for these repos — don't guess at existing patterns.
    """
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    results = client.query_points("code", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found."
    parts = []
    for r in results:
        p = r.payload
        header = (
            f"**{p['repo']}/{p['file']}** "
            f"lines {p['start_line']}-{p['end_line']} "
            f"({p.get('language', '')}) — score: {round(r.score, 3)}"
        )
        url = p.get("github_url", "")
        parts.append(f"{header}\n{url}\n\n{p['text']}" if url else f"{header}\n\n{p['text']}")
    return "\n\n---\n\n".join(parts)


_reindex_lock = threading.Lock()
_reindex_state: dict = {"running": False, "started_at": None, "output": [], "error": None, "done": False}


def _stream(cmd: list[str], label: str, timeout: int) -> None:
    """Run cmd, streaming each output line to logger and _reindex_state."""
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
    """Check whether a reindex is running or finished, and see its output log.

    Call this after reindex() to monitor progress. Returns elapsed time, status,
    streamed output lines, and any errors.
    """
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


def _merge_onboarding(existing: str) -> str:
    """Merge onboarding template with existing CLAUDE.md content."""
    sections = {
        "## MCP Setup": "## MCP Setup (if not connected)",
        "## Cortex Tools": "## Cortex Tools",
        "## Preferences": "## Preferences",
    }

    result = existing.rstrip()
    added = []

    # Check which sections already exist
    for marker, full_header in sections.items():
        if marker.lower() in existing.lower() or "cortex" in existing.lower() and "search_notes" in existing.lower():
            continue  # Section exists, skip

        # Find section in template
        template_lines = ONBOARDING_TEMPLATE.split("\n")
        in_section = False
        section_content = []

        for line in template_lines:
            if line.startswith(full_header) or line.startswith(marker):
                in_section = True
                section_content.append(line)
            elif in_section and line.startswith("## "):
                break  # Next section started
            elif in_section:
                section_content.append(line)

        if section_content:
            added.append("\n".join(section_content).rstrip())

    if not added:
        return existing + "\n\n<!-- Cortex onboarding: all sections already present -->"

    # Add Cortex header if not present
    if "# cortex" not in existing.lower() and "## cortex" not in existing.lower():
        result += "\n\n# Cortex Onboarding"

    result += "\n\n" + "\n\n".join(added)
    return result


@mcp.tool()
def get_onboarding(existing_content: str = "") -> str:
    """Get onboarding instructions for CLAUDE.md.

    Returns setup instructions, tool usage, and user preferences.

    Args:
        existing_content: If provided, merges with existing CLAUDE.md content,
                         adding only missing sections. Pass empty string for
                         full template.

    Call this when:
    - Starting a new project that should use Cortex
    - User asks how to set up Cortex in a new repo
    - User wants their preferences documented in a project

    Usage:
    1. Claude Code reads existing CLAUDE.md (if any)
    2. Pass content to get_onboarding(existing_content=...)
    3. Write merged result back to CLAUDE.md
    """
    if existing_content.strip():
        return _merge_onboarding(existing_content)
    return ONBOARDING_TEMPLATE


@mcp.prompt()
def onboarding() -> str:
    """Set up Cortex and user preferences for this project.

    Run /onboarding in any new project to configure:
    - CLAUDE.md with Cortex tools + preferences
    - Git user config
    - Install missing tools (rtk, caveman)
    """
    return f"""Set up Cortex for this project. Execute this checklist:

## 1. CLAUDE.md
Read existing CLAUDE.md (if any). Merge with this config, avoiding duplicates:

{ONBOARDING_TEMPLATE}

Write merged result to CLAUDE.md.

## 2. Git Config
Run for this repo:
```bash
rtk git config user.name "Xoudusz" && rtk git config user.email "da@w23.at"
```

## 3. Check RTK
Run `rtk --version`. If fails, install:
```bash
cargo install rtk
```

## 4. Check Caveman Skill
Run `claude skill list`. If caveman missing:
```bash
claude skill add caveman:caveman
```

## 5. Verify Cortex
Test connection: call `search_notes("test query")`. Should return results or "No results found."

Report status of each step when done."""


class _NotesHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer: threading.Timer | None = None

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
            # Unprotected paths:
            # - /health: healthchecks (no auth)
            # - /webhook: GitHub webhooks (HMAC auth)
            # - /register, /.well-known/*: OAuth discovery (404 fallback)
            # - /, /api/*: Web UI + API (Authelia handles auth at proxy level)
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
    """Return JSON 404 for OAuth discovery paths so MCP clients parse cleanly."""
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
    with _reindex_lock:
        if _reindex_state["running"]:
            log.info("[webhook] push received but reindex already running")
            return JSONResponse({"status": "reindex already running"})
        threading.Thread(target=_run_reindex, args=(False, True, repo), daemon=True).start()
    log.info("[webhook] push on %s → code reindex triggered", repo or "unknown")
    return JSONResponse({"status": "ok", "repo": repo})


def _start_watcher():
    if not os.path.isdir(NOTES_PATH):
        log.warning("[watcher] notes path %s not found, skipping", NOTES_PATH)
        return
    observer = Observer()
    observer.schedule(_NotesHandler(), NOTES_PATH, recursive=True)
    observer.start()
    log.info("[watcher] watching %s for .md changes (debounce %ds)", NOTES_PATH, WATCH_DEBOUNCE)


# Web UI route handlers
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


class _NormalizeSSEPath:
    """Rewrite /sse to /sse/ in ASGI scope so Starlette Mount never issues 307 redirect."""
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http' and scope.get('path') == '/sse':
            scope = dict(scope)
            scope['path'] = '/sse/'
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
        Route("/.well-known/oauth-authorization-server", oauth_not_found),
        Route("/.well-known/openid-configuration", oauth_not_found),
        Route("/register", oauth_not_found, methods=["POST"]),
        Mount("/sse", app=sse_app),
    ])
    app = _NormalizeSSEPath(_APIKeyMiddleware(starlette_app))
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
