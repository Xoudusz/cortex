"""Shared result formatters for MCP search tools — used by server and local modes."""

import time
from datetime import datetime, timezone


def strip_embed_header(text: str) -> str:
    """Drop the synthetic `# repo/path (lines)` / path-token / framework lines the chunker
    prepends for embedding — they only cost tokens in a result."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and lines[i].startswith("# "):
        i += 1
    if i == 0:
        return text
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "\n".join(lines[i:])


def _display_path(p: dict, fallback_prefix: str = "") -> str:
    """Absolute POSIX path when the index recorded a root (local mode), else repo-relative."""
    root = p.get("root")
    if root:
        return f"{root}/{p['file']}"
    return f"{fallback_prefix}/{p['file']}" if fallback_prefix else p["file"]


def fmt_age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def fmt_index_roots(roots: dict, now: float | None = None) -> list:
    """One line per index root: `path @head (age ago) notes=N code=M`."""
    now = now or time.time()
    out = []
    for root, m in sorted(roots.items()):
        head = f" @{m['git_head']}" if m.get("git_head") else ""
        age = f" ({fmt_age(now - m['indexed_at'])} ago)" if m.get("indexed_at") else ""
        out.append(f"{root}{head}{age} notes={m.get('notes', 0)} code={m.get('code', 0)}")
    return out


def format_notes_parts(results) -> tuple:
    """Build parts list from note search results.

    Returns (parts, matched_files, matched_scores). Caller is responsible for:
    - computing ppr_block from matched_files/matched_scores and appending to parts
    - joining parts with '\\n\\n---\\n\\n'
    - updating stats['context_tokens_notes']
    """
    parts = []
    matched_files = []
    matched_scores = []
    for r in results:
        p = r.payload
        tags = p.get("tags", [])
        tag_str = f" `{'`, `'.join(tags)}`" if tags else ""
        text = p["text"]
        heading = p.get("heading", "")
        if heading and text.startswith(heading + "\n"):
            text = text[len(heading):].lstrip("\n")  # chunk text repeats the heading
        parts.append(
            f"**{_display_path(p)} > {heading}** (score: {round(r.score, 3)}){tag_str}\n\n{text}"
        )
        matched_files.append(p.get("file", ""))
        matched_scores.append(r.score)
    return parts, matched_files, matched_scores


def format_code_results(deduped) -> str:
    """Build formatted string from scored/deduped code search results.

    Input: list of (boosted_score, qdrant_point, file_meta) tuples.
    Caller is responsible for updating stats['context_tokens_code'].
    """
    parts = []
    for boosted_score, r, file_meta in deduped:
        p = r.payload
        centrality = file_meta.get("centrality")
        community = file_meta.get("community_id")
        header = (
            f"**{_display_path(p, p.get('repo', ''))}** "
            f"lines {p['start_line']}-{p['end_line']} "
            f"({p.get('language', '')}) — score: {round(boosted_score, 3)}"
        )
        if centrality is not None:
            header += f" · centrality: {centrality}"
        if community is not None:
            header += f" · community: {community}"
        url = p.get("github_url", "")
        text = strip_embed_header(p["text"])
        parts.append(f"{header}\n{url}\n\n{text}" if url else f"{header}\n\n{text}")
    return "\n\n---\n\n".join(parts)


def _num(stats: dict, key: str):
    v = stats.get(key, 0)
    return v if isinstance(v, (int, float)) else 0


def _savings_line(stats: dict, k) -> str:
    oc, on, mo = _num(stats, "tokens_observed_code"), _num(stats, "tokens_observed_notes"), _num(stats, "tokens_modeled_code")
    return (
        f"  tokens avoided: observed={k(oc + on)} (code={k(oc)} notes={k(on)}) modeled={k(mo)} total={k(oc + on + mo)}"
        f" · hits measured={_num(stats, 'savings_hits_measured')} unmeasured={_num(stats, 'savings_hits_unmeasured')} (~bytes/4 est.)"
    )


def _by_line(stats: dict, field: str, label: str, k) -> str:
    """'  <label>: name=total ...' top 5 by observed+modeled, '+N more' for the rest."""
    by = stats.get(field)
    if not isinstance(by, dict) or not by:
        return ""
    rows = [(u, (b.get("observed", 0) or 0) + (b.get("modeled", 0) or 0))
            for u, b in by.items() if isinstance(b, dict)]
    if not rows:
        return ""
    rows.sort(key=lambda r: -r[1])
    out = f"  {label}: " + " ".join(f"{u}={k(t)}" for u, t in rows[:5])
    if len(rows) > 5:
        out += f" +{len(rows) - 5} more"
    return out


_STATUS_HINTS = {
    "index_missing": "No index exists for this workspace yet.",
    "index_empty": "The index exists but holds no chunks.",
    "reindex_in_progress": "A reindex is running; results will appear when it finishes.",
    "no_match": "Index is populated but nothing matched this query. Rephrase or broaden the query.",
    "repo_not_indexed": "No graph data for this repo.",
}


def fmt_status(code: str, hint: str | None = None, next_call: str = "") -> str:
    """Typed recovery state; callers put it on the first line of tool output."""
    hint = hint if hint is not None else _STATUS_HINTS.get(code, "")
    return f"status: {code}\n{hint}\nnext: {next_call}"


def classify_empty(exists: bool, points: int, reindexing: bool) -> str:
    if (not exists or not points) and reindexing:
        return "reindex_in_progress"
    if not exists:
        return "index_missing"
    if not points:
        return "index_empty"
    return "no_match"


def fmt_stats(v: str, stats: dict, current: bool = False) -> str:
    """Format stats block for one version. Safe for both server and local stats dicts."""
    total_searches = stats.get("search_code_calls", 0) + stats.get("search_notes_calls", 0) + stats.get("search_all_calls", 0)
    ppr_rate = (
        f"{stats['ppr_fires'] / stats['search_notes_calls'] * 100:.1f}%"
        if stats.get("search_notes_calls", 0) > 0 else "—"
    )
    avg_ppr = round(stats["ppr_results_added"] / stats["ppr_fires"], 1) if stats.get("ppr_fires", 0) > 0 else "—"
    cold_loads = stats.get("graph_cache_cold_loads", 0)
    total_cache = stats.get("graph_cache_hits", 0) + stats.get("graph_cache_misses", 0) + cold_loads
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
            period += f" -> {last[:10]}"
        lines.append(f"  period: {period}")

    lines += [
        f"  searches: code={stats.get('search_code_calls', 0)} notes={stats.get('search_notes_calls', 0)} all={stats.get('search_all_calls', 0)}  total={total_searches}  (notes {notes_pct})",
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
    ctx_notes = stats.get("context_tokens_notes", 0)
    ctx_code = stats.get("context_tokens_code", 0)
    ctx_total = ctx_notes + ctx_code

    def _k(n):
        return f"{n // 1000}k" if n >= 1000 else str(n)

    lines += [
        f"  context injected: notes={_k(ctx_notes)} code={_k(ctx_code)}  total={_k(ctx_total)} tokens (~chars/4 est.)",
        _savings_line(stats, _k),
    ]
    by_repo = _by_line(stats, "savings_by_repo", "by repo", _k)
    if by_repo:
        lines.append(by_repo)
    by_user = _by_line(stats, "savings_by_user", "by user", _k)
    if by_user:
        lines.append(by_user)
    lines += [
        f"  graph cache: {cache_rate} ({stats.get('graph_cache_hits', 0)}/{total_cache})  cold={cold_loads}",
        f"  embed cache skipped: notes={stats.get('embed_cache_notes', 0)} code={stats.get('embed_cache_code', 0)}",
        f"  reindexes: {stats.get('reindex_count', 0)}",
    ]
    return "\n".join(lines)
