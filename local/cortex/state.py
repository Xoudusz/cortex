"""Runtime state and graph cache for cortex local mode."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import data_dir, stats_file, VERSION
from .core.savings import snapshot as _snapshot

_graph_cache: dict = {}
_stats: dict = {}


def _default_stats() -> dict:
    return {
        "search_code_calls": 0,
        "centrality_lift_total": 0.0,
        "centrality_lift_count": 0,
        "search_notes_calls": 0,
        "ppr_fires": 0,
        "ppr_results_added": 0,
        "graph_cache_hits": 0,
        "graph_cache_misses": 0,
        "reindex_count": 0,
        "total_results_code": 0,
        "total_results_notes": 0,
        "context_tokens_notes": 0,
        "context_tokens_code": 0,
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
    defaults = _default_stats()
    try:
        sf = stats_file()
        if sf.exists():
            data = json.loads(sf.read_text())
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


def save_stats() -> None:
    try:
        sf = stats_file()
        existing: dict = {}
        if sf.exists():
            existing = json.loads(sf.read_text()).get("versions", {})
        existing[VERSION] = {**_snapshot(_stats), "last_saved": datetime.now(timezone.utc).isoformat()}
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps({"versions": existing}, indent=2))
    except Exception:
        pass


_last_save: float = 0.0


def maybe_save_stats(min_interval: float = 5.0) -> None:
    """Throttled save_stats so searches persist without a disk write per call."""
    global _last_save
    now = time.monotonic()
    if now - _last_save >= min_interval:
        _last_save = now
        save_stats()


def get_graph_meta(repo_name: str) -> dict:
    if repo_name in _graph_cache:
        _stats["graph_cache_hits"] += 1
        return _graph_cache[repo_name]
    path = data_dir() / f"graph_{repo_name}.json"
    if not path.exists():
        _stats["graph_cache_misses"] += 1
        return {}
    try:
        data = json.loads(path.read_text())
        meta = {n["id"]: n for n in data.get("nodes", []) if "id" in n}
        _graph_cache[repo_name] = meta
        _stats["graph_cache_misses"] += 1
        return meta
    except Exception:
        _stats["graph_cache_misses"] += 1
        return {}


def invalidate_graph_cache(repo_name: str = "") -> None:
    if repo_name:
        _graph_cache.pop(repo_name, None)
    else:
        _graph_cache.clear()


_stats = _load_stats()
