#!/usr/bin/env python3
"""Global runtime state, stats lifecycle, and code graph cache for cortex-mcp."""

import json
import logging
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, STATS_FILE, VERSION, WORKSPACE
from savings import snapshot as _snapshot
import users as _users

log = logging.getLogger("cortex")

# Append-only event logs kept in memory; capped at 50 entries each.
_webhook_log: list = []
_reindex_log: list = []

# In-memory cache: "workspace/repo_name" → {file_path: node_metadata_dict}
_graph_cache: dict = {}

_active_workspace: str = WORKSPACE  # used only when no request user is bound (auth off, startup)

# Per-request identity. Bound by the HTTP middleware (routes) and by CortexMCP.call_tool (MCP tools,
# which run outside the POST request's task), and by the reindex worker for each job.
_current_user: ContextVar = ContextVar("cortex_user", default=None)
_current_ws: ContextVar = ContextVar("cortex_ws", default=None)


def bind_request(user: str | None, ws: str | None = None) -> tuple:
    """Bind user + workspace (default: the user's remembered one) to this context; returns reset tokens."""
    if user is not None and ws is None:
        ws = _users.get_active_ws(user)
    return _current_user.set(user), _current_ws.set(ws)


def unbind_request(tokens: tuple) -> None:
    _current_user.reset(tokens[0])
    _current_ws.reset(tokens[1])


def bind_workspace(ws: str):
    """Bind only the workspace (reindex worker thread). Returns a reset token."""
    return _current_ws.set(ws)


def unbind_workspace(token) -> None:
    _current_ws.reset(token)


def current_user() -> str | None:
    return _current_user.get()


def get_active_workspace() -> str:
    ws = _current_ws.get()
    if ws:
        return ws
    if _current_user.get() is not None:
        # a bound user without any workspace must never fall through to the admin's "default"
        raise PermissionError("No workspace available. Ask the admin to grant you one.")
    return _active_workspace


def set_active_workspace(name: str) -> None:
    global _active_workspace
    user = _current_user.get()
    if user is not None:
        _users.set_active_ws(user, name)
        _current_ws.set(name)
    else:
        _active_workspace = name


def _workspace_data_dir(ws: str = "") -> Path:
    ws = ws or get_active_workspace()
    if ws == "default":
        return DATA_DIR
    return DATA_DIR / ws


def _default_stats() -> dict:
    """Return a zero-valued stats dict for the current version."""
    return {
        "search_code_calls": 0,
        "centrality_lift_total": 0.0,
        "centrality_lift_count": 0,
        "search_notes_calls": 0,
        "search_all_calls": 0,
        "ppr_fires": 0,
        "ppr_results_added": 0,
        "graph_cache_hits": 0,
        "graph_cache_misses": 0,
        "graph_cache_cold_loads": 0,
        "reindex_count": 0,
        "embed_cache_notes": 0,
        "embed_cache_code": 0,
        "total_results_code": 0,
        "total_results_notes": 0,
        "context_tokens_notes": 0,
        "context_tokens_code": 0,
        "ppr_nx_missing": 0,
        "ppr_graph_missing": 0,
        "ppr_no_matches": 0,
        "ppr_below_threshold": 0,
        "ppr_exception": 0,
        "tokens_observed_code": 0,
        "tokens_observed_notes": 0,
        "tokens_modeled_code": 0,
        "savings_hits_measured": 0,
        "savings_hits_unmeasured": 0,
        "savings_by_repo": {},
        "savings_by_user": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_stats() -> dict:
    """Load stats for the current VERSION from disk, merging with defaults."""
    defaults = _default_stats()
    try:
        if STATS_FILE.exists():
            data = json.loads(STATS_FILE.read_text())
            saved = data.get("versions", {}).get(VERSION, {})
            if saved:
                merged = {**defaults, **saved}
                for k in ("savings_by_repo", "savings_by_user"):
                    if not isinstance(merged.get(k), dict):
                        merged[k] = {}
                return merged
    except Exception:
        pass
    return defaults


def _load_all_stats() -> dict:
    """Return all persisted version stats for cross-version comparison."""
    try:
        if STATS_FILE.exists():
            return json.loads(STATS_FILE.read_text()).get("versions", {})
    except Exception:
        pass
    return {}


def _save_stats() -> None:
    """Persist the current in-memory stats under the current VERSION key."""
    try:
        existing: dict = {}
        if STATS_FILE.exists():
            try:
                existing = json.loads(STATS_FILE.read_text()).get("versions", {})
            except Exception:
                log.warning("stats file corrupt, resetting")
        existing[VERSION] = {**_snapshot(_stats), "last_saved": datetime.now(timezone.utc).isoformat()}
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.write_text(json.dumps({"versions": existing}, indent=2))
    except Exception as e:
        log.warning("stats save failed: %s", e)


def _stats_saver() -> None:
    """Background thread: flush stats to disk every 60 seconds."""
    while True:
        time.sleep(60)
        _save_stats()


def _get_code_graph_meta(repo_name: str) -> dict:
    """Return graph node metadata for repo_name, using the in-memory cache.

    Maps file path → node dict (centrality, community_id, imports, imported_by).
    Returns an empty dict when no graph data exists for the repo.
    """
    ws = get_active_workspace()
    cache_key = f"{ws}/{repo_name}"
    if cache_key in _graph_cache:
        _stats["graph_cache_hits"] += 1
        return _graph_cache[cache_key]
    path = _workspace_data_dir(ws) / f"graph_{repo_name}.json"
    if not path.exists():
        _stats["graph_cache_misses"] += 1
        return {}
    try:
        data = json.loads(path.read_text())
        meta = {n["id"]: n for n in data.get("nodes", []) if "id" in n}
        _graph_cache[cache_key] = meta
        _stats["graph_cache_cold_loads"] += 1
        return meta
    except Exception:
        _stats["graph_cache_misses"] += 1
        return {}


def _invalidate_graph_cache(repo_name: str = "") -> None:
    """Evict repo_name from the graph cache, or clear everything if empty."""
    if repo_name:
        ws = get_active_workspace()
        _graph_cache.pop(f"{ws}/{repo_name}", None)
    else:
        _graph_cache.clear()


# Initialized at import time so all modules share the same counters.
_stats: dict = _load_stats()
