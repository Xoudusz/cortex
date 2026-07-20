"""Cortex local MCP server — stdio transport, all 8 tools, embedded Qdrant."""

import json
import threading
import time
from pathlib import Path


from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, Fusion, SparseVector

from .config import (
    qdrant_path, data_dir, stats_file, VERSION, VECTOR_SIZE,
    WORKSPACES_DIR, get_active_workspace, set_active_workspace,
    get_workspace_dir, PPR_THRESHOLD, get_config,
)
from .embedder import embed, sparse_embed
from .state import _stats, get_graph_meta, save_stats, invalidate_graph_cache
from .indexer import index_path
from .core.formatters import format_notes_parts, format_code_results, fmt_stats

mcp = FastMCP("cortex")


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
_reindex_path: str = ""


def _qdrant() -> QdrantClient:
    return QdrantClient(path=qdrant_path())


# ── Reindex ─────────────────────────────────────────────────────────────────

def _run_reindex(path_str: str) -> None:
    _reindex_state.update(running=True, started_at=time.time(), output=[], error=None, done=False)
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            index_path(Path(path_str))
        _reindex_state["output"] = buf.getvalue().splitlines()
        _stats["reindex_count"] += 1
    except Exception as e:
        _reindex_state["error"] = str(e)
    finally:
        _reindex_state["running"] = False
        _reindex_state["done"] = True
        save_stats()


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
    return out


@mcp.tool()
def search_code(query: str, limit: int = 5) -> str:
    """Search source code across indexed directories semantically.

    Results are re-ranked by centrality (highly-imported files score higher).
    Returns code chunks with file path, line numbers, language, score, centrality, and community.
    """
    _stats["search_code_calls"] += 1
    out, log_entries = _search_code(query, limit)
    _log_search("search_code", query, log_entries)
    return out


@mcp.tool()
def search_all(query: str, limit: int = 5) -> str:
    """Search both notes and code simultaneously.

    Use when unsure whether the answer is in notes or code,
    or when you want a combined view across both collections.
    """
    _stats["search_notes_calls"] += 1
    _stats["search_code_calls"] += 1
    notes_out, matched_files, matched_scores = _search_notes(query, limit)
    code_out, log_entries = _search_code(query, limit)
    _log_search("search_all", query, log_entries)
    return f"## Notes\n\n{notes_out}\n\n## Code\n\n{code_out}"


@mcp.tool()
def reindex(path: str = "") -> str:
    """Re-index a path into the local Qdrant database.

    Runs async — returns immediately. Call reindex_status() to check progress.
    path: directory to index (defaults to last indexed path).
    """
    global _reindex_path
    target = path or _reindex_path
    if not target:
        return "Error: no path specified and no previous path recorded. Pass a path to index."
    _reindex_path = target
    if _reindex_state["running"]:
        return "Reindex already running. Call reindex_status() to check progress."
    threading.Thread(target=_run_reindex, args=(target,), daemon=True).start()
    return f"Reindex queued for '{target}'. Use reindex_status() to check progress."


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
    return fmt_stats(VERSION, _stats, current=True)


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
    return f"Switched to workspace '{name}'. search_code and search_notes now use this workspace's index."


@mcp.tool()
def list_workspaces() -> str:
    """List all cortex workspaces and their status.

    Shows which workspace is currently active and whether each has an index.
    """
    active = get_active_workspace()
    if not WORKSPACES_DIR.exists():
        return f"No workspaces found. Active: '{active}' (not yet indexed)."
    workspaces = sorted([d.name for d in WORKSPACES_DIR.iterdir() if d.is_dir()])
    if not workspaces:
        return f"No workspaces found. Active: '{active}'."
    lines = [f"Active workspace: {active}\n"]
    for ws in workspaces:
        marker = "* " if ws == active else "  "
        has_index = (WORKSPACES_DIR / ws / "qdrant").exists()
        lines.append(f"{marker}{ws} ({'indexed' if has_index else 'empty'})")
    return "\n".join(lines)


def run() -> None:
    """Entry point for stdio MCP server."""
    cfg = get_config()
    if cfg["watch"]["enabled"]:
        last = cfg["index"].get("last_path", "")
        if last and Path(last).exists():
            from .watcher import CortexWatcher
            CortexWatcher(Path(last), cfg["watch"]["debounce_seconds"]).start()
    mcp.run(transport="stdio")
