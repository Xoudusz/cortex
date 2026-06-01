#!/usr/bin/env python3
"""FastMCP instance and all MCP tools/prompts for cortex."""

import json
import logging
import time
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient

from config import HOST, PORT, QDRANT_URL, DATA_DIR, VERSION, embed
from state import _stats, _get_code_graph_meta, _load_all_stats
from onboarding import ONBOARDING_TEMPLATE, _merge_onboarding
from reindex import _enqueue, _reindex_state

log = logging.getLogger("cortex")

mcp = FastMCP("cortex", host=HOST, port=PORT)


def _augment_with_ppr(matched_files: list, matched_scores: list, graph_path) -> str | None:
    """Run PPR over wikilinks; return formatted extra block or None. Updates _stats counters."""
    try:
        from graph import ppr_augment
    except Exception:
        _stats["ppr_nx_missing"] += 1
        return None
    try:
        if not graph_path.exists():
            _stats["ppr_graph_missing"] += 1
            return None
        nodes = {
            n["id"] if isinstance(n, dict) else n
            for n in json.loads(graph_path.read_text()).get("nodes", [])
        }
        if not any(f in nodes for f in matched_files):
            _stats["ppr_no_matches"] += 1
            return None
        extras, reason = ppr_augment(matched_files, matched_scores, graph_path, _return_reason=True)
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
    except Exception:
        pass
    return None


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
    _stats["search_notes_calls"] += 1
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    results = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found."
    _stats["total_results_notes"] += len(results)
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
    ppr_block = _augment_with_ppr(matched_files, matched_scores, DATA_DIR / "graph_notes.json")
    if ppr_block:
        parts.append(ppr_block)
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
    _stats["search_code_calls"] += 1
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
        if centrality > 0:
            _stats["centrality_lift_total"] += round(boosted - r.score, 4)
            _stats["centrality_lift_count"] += 1
        scored.append((boosted, r, file_meta))
    scored.sort(key=lambda x: -x[0])
    seen_files: set = set()
    deduped = []
    for item in scored:
        key = f"{item[1].payload.get('repo', '')}/{item[1].payload.get('file', '')}"
        if key not in seen_files:
            seen_files.add(key)
            deduped.append(item)
        if len(deduped) >= limit:
            break
    _stats["total_results_code"] += len(deduped)
    parts = []
    for boosted_score, r, file_meta in deduped:
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
    _enqueue(notes, code, repo, files=None)
    q = _reindex_state["queue_depth"]
    return f"Reindex queued (position {q}). Use reindex_status() to check progress."


@mcp.tool()
def reindex_status() -> str:
    """Check whether a reindex is running or finished, and see its output log."""
    s = _reindex_state
    q = s.get("queue_depth", 0)
    if s["started_at"] is None:
        idle = "No reindex has been run yet."
        return idle + (f" {q} jobs queued." if q else "")
    elapsed = time.time() - s["started_at"]
    status = "running" if s["running"] else "done"
    header = f"Status: {status} ({elapsed:.0f}s elapsed)"
    if q:
        header += f" — {q} more job(s) queued"
    lines = [header]
    if s["output"]:
        lines.append("\n".join(s["output"]))
    if s["error"]:
        lines.append(f"Error: {s['error']}")
    return "\n\n".join(lines)


def _fmt_version_stats(v: str, stats: dict, current: bool = False) -> str:
    """Format per-version stats block for display."""
    total_searches = stats.get("search_code_calls", 0) + stats.get("search_notes_calls", 0)
    ppr_rate = f"{stats['ppr_fires'] / stats['search_notes_calls'] * 100:.1f}%" if stats.get("search_notes_calls", 0) > 0 else "—"
    avg_ppr = round(stats["ppr_results_added"] / stats["ppr_fires"], 1) if stats.get("ppr_fires", 0) > 0 else "—"
    total_cache = stats.get("graph_cache_hits", 0) + stats.get("graph_cache_misses", 0)
    cache_rate = f"{stats['graph_cache_hits'] / total_cache * 100:.1f}%" if total_cache > 0 else "—"
    avg_lift = round(stats["centrality_lift_total"] / stats["centrality_lift_count"], 4) if stats.get("centrality_lift_count", 0) > 0 else 0
    total_results = stats.get("total_results_code", 0) + stats.get("total_results_notes", 0)
    avg_results = round(total_results / total_searches, 1) if total_searches > 0 else "—"
    notes_pct = f"{stats['search_notes_calls'] / total_searches * 100:.0f}%" if total_searches > 0 else "—"

    label = f"{v} (current)" if current else v
    lines = [label]

    started = stats.get("started_at", "")
    if current and started:
        try:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(started)
            h, rem = divmod(int(delta.total_seconds()), 3600)
            m = rem // 60
            lines.append(f"  uptime: {h}h {m}m")
        except Exception:
            pass
    elif started:
        last = stats.get("last_saved", "")
        period = started[:10]
        if last:
            period += f" → {last[:10]}"
        lines.append(f"  period: {period}")

    lines += [
        f"  searches: code={stats.get('search_code_calls', 0)} notes={stats.get('search_notes_calls', 0)}  total={total_searches}  (notes {notes_pct})",
        f"  results: code={stats.get('total_results_code', 0)} notes={stats.get('total_results_notes', 0)}  avg/search={avg_results}",
        f"  centrality lift avg: {avg_lift} (across {stats.get('centrality_lift_count', 0)} results)",
        f"  PPR: {stats.get('ppr_fires', 0)} fires ({ppr_rate} of note searches) · +{stats.get('ppr_results_added', 0)} results · avg {avg_ppr}/fire",
    ]
    _ppr_diag = {k: stats.get(k, 0) for k in ("ppr_nx_missing", "ppr_graph_missing", "ppr_no_matches", "ppr_below_threshold", "ppr_exception")}
    if any(_ppr_diag.values()):
        lines.append(
            f"  PPR misses: nx={_ppr_diag['ppr_nx_missing']} graph={_ppr_diag['ppr_graph_missing']}"
            f" no_match={_ppr_diag['ppr_no_matches']} below_threshold={_ppr_diag['ppr_below_threshold']}"
            f" exception={_ppr_diag['ppr_exception']}"
        )
    lines += [
        f"  graph cache: {cache_rate} ({stats.get('graph_cache_hits', 0)}/{total_cache})",
        f"  reindexes: {stats.get('reindex_count', 0)}",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_stats(all: bool = False) -> str:
    """Return cortex efficiency metrics.

    all=False (default): current version stats with uptime, search mix, PPR effectiveness, cache, centrality lift.
    all=True: all persisted versions side-by-side for comparison.
    """
    if all:
        versions = _load_all_stats()
        if not versions:
            return "No persisted stats found. Stats save every 60s."
        blocks = []
        for v in sorted(versions):
            g = versions[v]
            blocks.append(_fmt_version_stats(v, g, current=(v == VERSION)))
        return "=== All versions ===\n\n" + "\n\n".join(blocks)

    queue_depth = _reindex_state.get("queue_depth", 0)
    out = _fmt_version_stats(VERSION, _stats, current=True)
    if queue_depth:
        out += f"\n  reindex queue depth: {queue_depth}"
    return out


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
