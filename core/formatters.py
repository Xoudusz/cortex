"""Shared result formatters for MCP search tools — used by server and local modes."""

from datetime import datetime, timezone


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
        parts.append(
            f"**{p['file']} > {p['heading']}** (score: {round(r.score, 3)}){tag_str}\n\n{p['text']}"
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


def fmt_stats(v: str, stats: dict, current: bool = False) -> str:
    """Format stats block for one version. Safe for both server and local stats dicts."""
    total_searches = stats.get("search_code_calls", 0) + stats.get("search_notes_calls", 0)
    ppr_rate = (
        f"{stats['ppr_fires'] / stats['search_notes_calls'] * 100:.1f}%"
        if stats.get("search_notes_calls", 0) > 0 else "—"
    )
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
            period += f" -> {last[:10]}"
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
    ctx_notes = stats.get("context_tokens_notes", 0)
    ctx_code = stats.get("context_tokens_code", 0)
    ctx_total = ctx_notes + ctx_code

    def _k(n):
        return f"{n // 1000}k" if n >= 1000 else str(n)

    lines += [
        f"  context injected: notes={_k(ctx_notes)} code={_k(ctx_code)}  total={_k(ctx_total)} tokens (~chars/4 est.)",
        f"  graph cache: {cache_rate} ({stats.get('graph_cache_hits', 0)}/{total_cache})",
        f"  embed cache skipped: notes={stats.get('embed_cache_notes', 0)} code={stats.get('embed_cache_code', 0)}",
        f"  reindexes: {stats.get('reindex_count', 0)}",
    ]
    return "\n".join(lines)
