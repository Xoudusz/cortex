#!/usr/bin/env python3
"""Search tools and helpers for cortex MCP server."""

import json
import logging
import time

from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, Fusion, SparseVector

from config import QDRANT_URL, DATA_DIR, embed, sparse_embed, collection_name, PPR_THRESHOLD
from state import _stats, _get_code_graph_meta, current_user, get_active_workspace, _workspace_data_dir
from repos import _load_repos
from formatters import format_notes_parts, format_code_results, strip_embed_header, fmt_status, classify_empty
from reindex import get_status as _reindex_status
import savings

log = logging.getLogger("cortex")


def _log_search(tool: str, query: str, top: list) -> None:
    try:
        entry = {"ts": time.time(), "tool": tool, "query": query, "top": top,
                 "user": current_user(), "ws": get_active_workspace()}
        with open(DATA_DIR / "search_log.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _build_search_code_description() -> str:
    repo_names = [r.split("/")[-1] for r in _load_repos()]
    repo_list = ", ".join(repo_names) if repo_names else "no repos indexed yet"
    return (
        "Search source code across the user's active repos semantically.\n\n"
        f"Indexed repos: {repo_list}.\n\n"
        "Call this proactively whenever:\n"
        "- Implementing a feature that touches one of these repos\n"
        "- Looking for where something is defined or how a pattern is used\n"
        "- Debugging — find related code before suggesting a fix\n"
        '- The user asks "how does X work" about one of their projects\n'
        "- Writing code that should match existing conventions in the repo\n\n"
        "Results are re-ranked by centrality (highly-imported files score higher).\n"
        "Returns code chunks with file path, line numbers, language, score, centrality, community, and GitHub link.\n"
        "Always search before writing code for these repos — don't guess at existing patterns."
    )


def _augment_with_ppr(matched_files: list, matched_scores: list, graph_path) -> str | None:
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
    except Exception:
        pass
    return None


def _empty_status(kind: str, ws: str, client, exc=None) -> str:
    """Typed recovery text for an empty/failed query. Re-raises exc when the collection is populated."""
    coll = collection_name(kind, ws)
    try:
        exists = client.collection_exists(coll)
        points = (client.get_collection(coll).points_count or 0) if exists else 0
    except Exception:
        if exc is not None:
            raise exc
        exists, points = False, 0
    code = classify_empty(exists, points, bool(_reindex_status().get("running")))
    if exc is not None and code == "no_match":
        raise exc
    if code == "reindex_in_progress":
        nxt = "reindex_status()"
    elif code == "no_match":
        nxt = f"search_{kind}(<rephrased query>)"
    else:
        nxt = f"reindex({kind}=True)"
    return fmt_status(code, None, nxt)


def _search_notes(query: str, limit: int = 5):
    ws = get_active_workspace()
    coll = collection_name("notes", ws)
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    try:
        idx, vals = sparse_embed(query)
        results = client.query_points(
            coll,
            prefetch=[
                Prefetch(query=vector, using=None, limit=limit * 2),
                Prefetch(query=SparseVector(indices=idx, values=vals), using="sparse", limit=limit * 2),
            ],
            query=Fusion.RRF,
            limit=limit,
            with_payload=True,
        ).points
    except Exception:
        try:
            results = client.query_points(coll, query=vector, limit=limit, with_payload=True).points
        except Exception as e:
            return _empty_status("notes", ws, client, e), [], []
    if not results:
        return _empty_status("notes", ws, client), [], []
    _stats["total_results_notes"] += len(results)
    parts, matched_files, matched_scores = format_notes_parts(results)
    user = current_user() or "anon"
    savings.record_notes(
        _stats, savings.SERVER_STORE, (user, ws),
        [(r.payload.get("file", ""), strip_embed_header(r.payload["text"]) or r.payload["text"]) for r in results],
        savings.notes_bytes_map(_workspace_data_dir(ws) / "graph_notes.json"), user=user,
    )
    ppr_block = _augment_with_ppr(matched_files, matched_scores, _workspace_data_dir(ws) / "graph_notes.json")
    if ppr_block:
        parts.append(ppr_block)
    out = "\n\n---\n\n".join(parts)
    _stats["context_tokens_notes"] += len(out) // 4
    return out, matched_files, matched_scores


def _search_code(query: str, limit: int = 5):
    ws = get_active_workspace()
    coll = collection_name("code", ws)
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    fetch_limit = min(limit * 3, 50)
    try:
        idx, vals = sparse_embed(query)
        results = client.query_points(
            coll,
            prefetch=[
                Prefetch(query=vector, using=None, limit=fetch_limit),
                Prefetch(query=SparseVector(indices=idx, values=vals), using="sparse", limit=fetch_limit),
            ],
            query=Fusion.RRF,
            limit=fetch_limit,
            with_payload=True,
        ).points
    except Exception:
        try:
            results = client.query_points(coll, query=vector, limit=fetch_limit, with_payload=True).points
        except Exception as e:
            return _empty_status("code", ws, client, e), []
    if not results:
        return _empty_status("code", ws, client), []
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
    user = current_user() or "anon"
    savings.record_code(
        _stats, savings.SERVER_STORE, (user, ws),
        [(it[1].payload.get("repo", ""), it[1].payload.get("file", ""),
          strip_embed_header(it[1].payload["text"]) or it[1].payload["text"], it[2]) for it in deduped],
        [(it[1].payload.get("repo", ""), it[1].payload.get("file", ""), it[2]) for it in scored
         if f"{it[1].payload.get('repo', '')}/{it[1].payload.get('file', '')}" not in seen_files],
        user=user,
    )
    log_entries = [
        {"repo": r.payload.get("repo", ""), "file": r.payload.get("file", ""), "score": round(bs, 3)}
        for bs, r, _ in deduped
    ]
    out = format_code_results(deduped)
    _stats["context_tokens_code"] += len(out) // 4
    return out, log_entries


def register_search(mcp) -> None:
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
        out, matched_files, matched_scores = _search_notes(query, limit)
        _log_search("search_notes", query, [
            {"file": f, "score": round(s, 3)} for f, s in zip(matched_files, matched_scores)
        ] if matched_files else [])
        return out

    @mcp.tool(description=_build_search_code_description())
    def search_code(query: str, limit: int = 5) -> str:
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
        _stats["search_all_calls"] += 1
        notes_out, matched_files, matched_scores = _search_notes(query, limit)
        code_out, log_entries = _search_code(query, limit)
        _log_search("search_all", query, log_entries)
        n_status, c_status = notes_out.startswith("status:"), code_out.startswith("status:")
        if n_status or c_status:
            # typed status must be the first line of the tool output
            lead = "\n\n".join(dict.fromkeys(o for o, st in ((notes_out, n_status), (code_out, c_status)) if st))
            notes_out = "(none)" if n_status else notes_out
            code_out = "(none)" if c_status else code_out
            return f"{lead}\n\n## Notes\n\n{notes_out}\n\n## Code\n\n{code_out}"
        return f"## Notes\n\n{notes_out}\n\n## Code\n\n{code_out}"
