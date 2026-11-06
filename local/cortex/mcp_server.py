"""Cortex local MCP server — stdio transport, embedded Qdrant.

stdout is the JSON-RPC channel: nothing in this process may print. Use logging (file).
"""

import json
import logging
import logging.handlers
import threading
import time
from pathlib import Path


from mcp.server.mcpserver import MCPServer
from qdrant_client.models import Prefetch, Fusion, SparseVector

from . import db
from .config import (
    data_dir, stats_file, VERSION,
    WORKSPACES_DIR, get_active_workspace, set_active_workspace,
    get_workspace_dir, PPR_THRESHOLD, get_config, ensure_index_schema,
    get_roots, read_index_meta,
)
from .embedder import embed, sparse_embed
from .state import _stats, get_graph_meta, save_stats, invalidate_graph_cache
from .indexer import index_path
from .core.formatters import (
    format_notes_parts, format_code_results, fmt_stats, fmt_age, fmt_index_roots,
)

mcp = MCPServer("cortex", version=VERSION)
log = logging.getLogger("cortex")


class _ListHandler(logging.Handler):
    def __init__(self, sink: list):
        super().__init__(logging.INFO)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record.getMessage())


def _log_search(tool: str, query: str, top: list) -> None:
    try:
        entry = {"ts": time.time(), "tool": tool, "query": query, "top": top}
        with open(data_dir() / "search_log.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


_reindex_state: dict = {
    "running": False, "started_at": None, "output": [], "error": None, "done": False,
}
_watcher = None
_watched: tuple = ()


def _qdrant():
    return db.client()


# ── Reindex ─────────────────────────────────────────────────────────────────

def _index_roots(paths: list, source: str) -> None:
    """Index paths one after another. Serialized with every other index run via db.index_lock."""
    with db.index_lock:
        _reindex_state.update(running=True, started_at=time.time(), output=[], error=None, done=False)
        # Capture indexer log lines for reindex_status().
        capture = _ListHandler(_reindex_state["output"])
        logging.getLogger("cortex").addHandler(capture)
        try:
            for path_str in paths:
                t0 = time.time()
                log.info("reindex (%s) started: %s", source, path_str)
                try:
                    index_path(Path(path_str))
                    _stats["reindex_count"] += 1
                    log.info("reindex finished: %s (%.0fs)", path_str, time.time() - t0)
                except BaseException as e:  # SystemExit from a locked db must not kill the thread silently
                    _reindex_state["error"] = str(e)
                    log.exception("reindex failed: %s", path_str)
        finally:
            logging.getLogger("cortex").removeHandler(capture)
            _reindex_state["running"] = False
            _reindex_state["done"] = True
            save_stats()
    _restart_watcher()  # pick up newly added roots


def _restart_watcher(force: bool = False) -> None:
    """(Re)start the file watcher for the active workspace's roots; no-op if they're unchanged."""
    global _watcher, _watched
    cfg = get_config()
    roots = get_roots() if cfg["watch"]["enabled"] else []
    key = (get_active_workspace(), tuple(sorted(roots)))
    if key == _watched and not force:
        return
    if _watcher is not None:
        _watcher.stop()
        _watcher = None
    _watched = key
    if not roots:
        return
    from .watcher import CortexWatcher
    _watcher = CortexWatcher(roots, cfg["watch"]["debounce_seconds"],
                             lambda root: _index_roots([root.as_posix()], "watcher"))
    _watcher.start()


def _index_header() -> str:
    """One line telling the agent how fresh the index is."""
    roots = read_index_meta().get("roots", {})
    if not roots:
        return "_index: empty - call reindex(path)_"
    now = time.time()
    parts = []
    for root, m in sorted(roots.items()):
        head = f"@{m['git_head']} " if m.get("git_head") else ""
        age = fmt_age(now - m["indexed_at"]) if m.get("indexed_at") else "?"
        parts.append(f"{root} {head}{age} ago")
    watching = " (auto-reindex on)" if _watcher is not None else " (auto-reindex off)"
    return "_index: " + "; ".join(parts) + watching + "_"


# ── PPR helper ───────────────────────────────────────────────────────────────

def _ppr_block(matched_files: list, matched_scores: list) -> str | None:
    try:
        from .core.notes_graph import ppr_augment
    except Exception:
        return None
    graph_path = data_dir() / "graph_notes.json"
    extras, reason = ppr_augment(matched_files, matched_scores, graph_path, threshold=PPR_THRESHOLD, _return_reason=True)
    if extras:
        _stats["ppr_fires"] += 1
        _stats["ppr_results_added"] += len(extras)
        lines = ["**Related via wikilinks (PPR):**"]
        for e in extras:
            lines.append(f"  -> {e['file']} (ppr: {e['ppr_score']})")
        return "\n".join(lines)
    if reason == "exception":
        _stats["ppr_exception"] += 1
    else:
        _stats["ppr_below_threshold"] += 1
    return None


# ── Tools ────────────────────────────────────────────────────────────────────

def _search_notes(query: str, limit: int = 5):
    client = _qdrant()
    vector = embed(query)
    try:
        idx, vals = sparse_embed(query)
        results = client.query_points(
            "notes",
            prefetch=[
                Prefetch(query=vector, using=None, limit=limit * 2),
                Prefetch(query=SparseVector(indices=idx, values=vals), using="sparse", limit=limit * 2),
            ],
            query=Fusion.RRF,
            limit=limit,
            with_payload=True,
        ).points
    except Exception:
        results = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found.", [], []
    _stats["total_results_notes"] += len(results)
    parts, matched_files, matched_scores = format_notes_parts(results)
    ppr = _ppr_block(matched_files, matched_scores)
    if ppr:
        parts.append(ppr)
    out = "\n\n---\n\n".join(parts)
    _stats["context_tokens_notes"] += len(out) // 4
    return out, matched_files, matched_scores


def _search_code(query: str, limit: int = 5):
    client = _qdrant()
    vector = embed(query)
    fetch_limit = min(limit * 3, 50)
    try:
        idx, vals = sparse_embed(query)
        results = client.query_points(
            "code",
            prefetch=[
                Prefetch(query=vector, using=None, limit=fetch_limit),
                Prefetch(query=SparseVector(indices=idx, values=vals), using="sparse", limit=fetch_limit),
            ],
            query=Fusion.RRF,
            limit=fetch_limit,
            with_payload=True,
        ).points
    except Exception:
        results = client.query_points("code", query=vector, limit=fetch_limit, with_payload=True).points
    if not results:
        return "No results found.", []
    scored = []
    for r in results:
        p = r.payload
        file_meta = get_graph_meta(p.get("repo", "")).get(p.get("file", ""), {})
        centrality = file_meta.get("centrality", 0.0)
        boosted = r.score * (1.0 + 0.2 * centrality)
        if centrality > 0:
            _stats["centrality_lift_total"] += round(boosted - r.score, 4)
            _stats["centrality_lift_count"] += 1
        scored.append((boosted, r, file_meta))
    scored.sort(key=lambda x: -x[0])
    seen: set = set()
    deduped = []
    for item in scored:
        key = f"{item[1].payload.get('repo', '')}/{item[1].payload.get('file', '')}"
        if key not in seen:
            seen.add(key)
            deduped.append(item)
        if len(deduped) >= limit:
            break
    _stats["total_results_code"] += len(deduped)
    log_entries = [
        {"repo": r.payload.get("repo", ""), "file": r.payload.get("file", ""), "score": round(bs, 3)}
        for bs, r, _ in deduped
    ]
    out = format_code_results(deduped)
    _stats["context_tokens_code"] += len(out) // 4
    return out, log_entries


@mcp.tool()
def search_notes(query: str, limit: int = 5) -> str:
    """Search the user's personal knowledge base semantically.

    Call this proactively whenever the user asks about:
    - Their projects, plans, ideas, or roadmap items
    - Personal context, goals, or decisions they may have documented
    - How something in their setup works
    - Anything that sounds like it could be in personal notes

    Returns matching note sections with file path, heading, score, and tags.
    PPR over wikilinks surfaces related notes beyond direct vector matches.
    """
    _stats["search_notes_calls"] += 1
    out, matched_files, matched_scores = _search_notes(query, limit)
    _log_search("search_notes", query, [
        {"file": f, "score": round(s, 3)} for f, s in zip(matched_files, matched_scores)
    ])
    log.info("search_notes %r -> %d hits", query, len(matched_files))
    return f"{_index_header()}\n\n{out}"


@mcp.tool()
def search_code(query: str, limit: int = 5) -> str:
    """Search source code across indexed directories semantically.

    Results are re-ranked by centrality (highly-imported files score higher).
    Returns code chunks with file path, line numbers, language, score, centrality, and community.
    """
    _stats["search_code_calls"] += 1
    out, log_entries = _search_code(query, limit)
    _log_search("search_code", query, log_entries)
    log.info("search_code %r -> %d hits", query, len(log_entries))
    return f"{_index_header()}\n\n{out}"


@mcp.tool()
def search_all(query: str, limit: int = 5) -> str:
    """Search both notes and code simultaneously.

    Use when unsure whether the answer is in notes or code,
    or when you want a combined view across both collections.
    limit applies per collection: limit=3 returns up to 3 notes AND up to 3 code hits.
    """
    _stats["search_notes_calls"] += 1
    _stats["search_code_calls"] += 1
    notes_out, matched_files, matched_scores = _search_notes(query, limit)
    code_out, log_entries = _search_code(query, limit)
    _log_search("search_all", query, log_entries)
    log.info("search_all %r -> notes=%d code=%d", query, len(matched_files), len(log_entries))
    return f"{_index_header()}\n\n## Notes\n\n{notes_out}\n\n## Code\n\n{code_out}"


@mcp.tool()
def reindex(path: str = "") -> str:
    """Re-index a directory into the local index (incremental: only changed files are re-embedded).

    Runs async — returns immediately. Call reindex_status() to check progress.
    path: directory to index; a new path is added as an index root and watched afterwards.
          Empty = re-index every existing root of the active workspace.
    """
    if path:
        p = Path(path).expanduser()
        if not p.is_dir():
            return f"Error: '{path}' is not a directory."
        targets = [p.resolve().as_posix()]
    else:
        targets = get_roots()
        if not targets:
            return "Error: nothing indexed yet in this workspace. Pass a path to index."
    if _reindex_state["running"] or db.index_lock.locked():
        return "Reindex already running. Call reindex_status() to check progress."
    threading.Thread(target=_index_roots, args=(targets, "tool"), daemon=True).start()
    return f"Reindex queued for {', '.join(targets)}. Use reindex_status() to check progress."


@mcp.tool()
def reindex_status() -> str:
    """Check whether a reindex is running or finished, and see its output log."""
    if _reindex_state["started_at"] is None:
        return "No reindex has been run yet. Call reindex(path='/your/path') to start."
    elapsed = time.time() - _reindex_state["started_at"]
    status = "running" if _reindex_state["running"] else "done"
    lines = [f"Status: {status} ({elapsed:.0f}s elapsed)"]
    if _reindex_state["output"]:
        lines.append("\n".join(_reindex_state["output"]))
    if _reindex_state["error"]:
        lines.append(f"Error: {_reindex_state['error']}")
    return "\n".join(lines)


@mcp.tool()
def get_stats(all: bool = False) -> str:
    """Return cortex efficiency metrics.

    all=False (default): current session stats.
    all=True: all persisted versions side-by-side.
    """
    if all:
        try:
            sf = stats_file()
            versions = json.loads(sf.read_text()).get("versions", {}) if sf.exists() else {}
        except Exception:
            versions = {}
        if not versions:
            return "No persisted stats found."
        blocks = []
        for v in sorted(versions):
            blocks.append(fmt_stats(v, versions[v], current=(v == VERSION)))
        return "\n\n".join(blocks)
    return _index_summary() + "\n\n" + fmt_stats(VERSION, _stats, current=True)


def _index_summary(ws: str | None = None) -> str:
    ws = ws or get_active_workspace()
    roots = read_index_meta(ws).get("roots", {})
    lines = [f"workspace: {ws}"]
    if not roots:
        lines.append("  index: empty")
    else:
        notes = sum(m.get("notes", 0) for m in roots.values())
        code = sum(m.get("code", 0) for m in roots.values())
        lines.append(f"  chunks: notes={notes} code={code}")
        lines += [f"  root: {line}" for line in fmt_index_roots(roots)]
    if ws == get_active_workspace():
        lines.append(f"  auto-reindex: {'on' if _watcher is not None else 'off'}")
    return "\n".join(lines)


@mcp.tool()
def get_neighbors(file: str, repo: str) -> str:
    """Show what a code file imports and what imports it (direct graph neighbors).

    Use when you want to explore structural connections around a file.
    Example: get_neighbors("src/lib/api/sonarr.ts", "arr-client")

    Requires graph data — run reindex first if empty.
    """
    meta = get_graph_meta(repo)
    if not meta:
        return f"No graph data for '{repo}'. Run reindex() first."
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
    """List all files in the same structural community/cluster.

    Use when you want to find everything structurally related to a file.
    Example: get_community("my-project", 0)

    Requires graph data — run reindex first if empty.
    """
    meta = get_graph_meta(repo)
    if not meta:
        return f"No graph data for '{repo}'. Run reindex() first."
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


@mcp.tool()
def get_onboarding(existing_content: str = "") -> str:
    """Get a CLAUDE.md template with Cortex search instructions pre-filled.

    No args: returns full template with placeholder sections.
    With existing_content: appends Cortex section if not already present.
    """
    cortex_section = """## Cortex (semantic search)

cortex is available as an MCP tool. Use it proactively:
- `search_notes(query)` — search personal knowledge base
- `search_code(query)` — search indexed code repositories
- `get_neighbors(file, repo)` — explore import graph for a file
- `get_community(repo, community_id)` — list files in a structural cluster
- `reindex(path)` — re-index a directory after changes
- `reindex_status()` — check reindex progress
"""
    if existing_content.strip():
        if "cortex" in existing_content.lower() or "search_notes" in existing_content:
            return existing_content
        return existing_content.rstrip() + "\n\n" + cortex_section
    return f"""# Project CLAUDE.md

## Stack
<!-- fill in: language, framework, key dependencies -->

## Commands
<!-- fill in: build, test, lint, run -->

## Structure
<!-- fill in: key directories and what they contain -->

## Conventions
<!-- fill in: naming, patterns, style -->

## Don't
<!-- fill in: things to avoid -->

{cortex_section}"""


@mcp.tool()
def switch_workspace(name: str) -> str:
    """Switch the active cortex workspace.

    Each workspace has its own isolated index (notes + code).
    Use when switching between work/personal/project contexts.
    Example: switch_workspace("work")
    """
    ws_dir = get_workspace_dir(name)
    if not ws_dir.exists():
        return (
            f"Workspace '{name}' does not exist.\n"
            f"Create it with: cortex workspace create {name}"
        )
    set_active_workspace(name)
    invalidate_graph_cache()
    db.reset()
    _restart_watcher(force=True)
    log.info("switched workspace to '%s'", name)
    return f"Switched to workspace '{name}'. search_code and search_notes now use this workspace's index."


@mcp.tool()
def list_workspaces() -> str:
    """List all cortex workspaces: active marker, index roots, chunk counts and index age."""
    active = get_active_workspace()
    if not WORKSPACES_DIR.exists():
        return f"No workspaces found. Active: '{active}' (not yet indexed)."
    workspaces = sorted([d.name for d in WORKSPACES_DIR.iterdir() if d.is_dir()])
    if not workspaces:
        return f"No workspaces found. Active: '{active}'."
    lines = [f"Active workspace: {active}\n"]
    for ws in workspaces:
        marker = "* " if ws == active else "  "
        lines.append(marker + _index_summary(ws).replace("\n", "\n  "))
    return "\n".join(lines)


@mcp.tool()
def get_log(lines: int = 100) -> str:
    """Return path and tail of the cortex log file. Share output with developer for troubleshooting."""
    log_path = data_dir() / "cortex.log"
    if not log_path.exists():
        return f"No log yet. Will be created at: {log_path}"
    try:
        all_lines = log_path.read_text(errors="replace").splitlines()
        tail = "\n".join(all_lines[-lines:])
        return f"Log: {log_path}\n\n{tail}"
    except Exception as e:
        return f"Error reading log: {e}\nPath: {log_path}"


def run() -> None:
    """Entry point for stdio MCP server."""
    log_path = data_dir() / "cortex.log"
    data_dir().mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )],
        force=True,
    )
    log.info("cortex %s starting (workspace: %s, log: %s)", VERSION, get_active_workspace(), log_path)
    ensure_index_schema()
    try:
        _restart_watcher()
    except Exception:
        log.exception("watcher failed to start")
    for line in _index_summary().splitlines():
        log.info(line)
    mcp.run(transport="stdio")
