#!/usr/bin/env python3
"""Repo registry persistence for cortex-mcp."""

import json
import os
from datetime import datetime, timezone

from config import REPOS_CONFIG, DATA_DIR, WORKSPACE
from state import get_active_workspace

DEFAULT_REPOS = [
    "Xoudusz/weakness-dex",
    "Xoudusz/mtgdle",
    "Xoudusz/tower-of-evolon",
    "Xoudusz/tower-of-evolon-backend",
    "Xoudusz/svelte-radio",
    "Xoudusz/cortex",
    "Xoudusz/riftracoons-web",
]


def _ws(workspace: str = "") -> str:
    """Explicit workspace, else the caller's active one (per-user when a request user is bound)."""
    return workspace or get_active_workspace() or WORKSPACE


def _repos_config_path(workspace: str = "") -> str:
    ws = _ws(workspace)
    if ws == "default":
        return REPOS_CONFIG
    return str(DATA_DIR / ws / "repos.json")


def ensure_workspace_repos(workspace: str) -> None:
    """Create an empty repos.json for a new workspace (else it would inherit DEFAULT_REPOS)."""
    path = _repos_config_path(workspace)
    if not os.path.exists(path):
        _save_repos_meta({"repos": [], "indexed_at": {}}, workspace)


def _load_repos_meta(workspace: str = "") -> dict:
    """Load repo metadata (repo list + indexed_at timestamps) from disk."""
    ws = _ws(workspace)
    path = _repos_config_path(ws)
    try:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"repos": data.get("repos", []), "indexed_at": data.get("indexed_at", {}),
                        "errors": data.get("errors", {})}
            if isinstance(data, list) and data:
                return {"repos": data, "indexed_at": {}}
    except Exception:
        pass
    # only the admin's own workspace falls back to the built-in repo list
    return {"repos": list(DEFAULT_REPOS) if ws == "default" else [], "indexed_at": {}}


def _load_repos(workspace: str = "") -> list:
    """Return the list of tracked repos as owner/name strings."""
    return _load_repos_meta(workspace)["repos"]


def _save_repos_meta(meta: dict, workspace: str = "") -> None:
    """Write the full repo metadata dict (repos + indexed_at) to disk."""
    path = _repos_config_path(workspace)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)


def _save_repos(repos: list, workspace: str = "") -> None:
    """Replace the tracked repo list on disk, preserving other metadata fields."""
    meta = _load_repos_meta(workspace)
    meta["repos"] = repos
    _save_repos_meta(meta, workspace)


def _record_index_result(repo_name: str, error: str | None, workspace: str = "") -> None:
    """Success: stamp indexed_at, clear the error. Failure: store the error, drop indexed_at
    (an 'indexed' badge must mean the repo's chunks are actually in the index)."""
    meta = _load_repos_meta(workspace)
    errors = meta.setdefault("errors", {})
    if error:
        errors[repo_name] = error[:500]
        meta.setdefault("indexed_at", {}).pop(repo_name, None)
    else:
        errors.pop(repo_name, None)
        meta.setdefault("indexed_at", {})[repo_name] = datetime.now(timezone.utc).isoformat()
    _save_repos_meta(meta, workspace)


def _update_indexed_at(repo_name: str, workspace: str = "") -> None:
    """Record the current UTC time as the last successful index time for repo_name."""
    meta = _load_repos_meta(workspace)
    meta.setdefault("indexed_at", {})[repo_name] = datetime.now(timezone.utc).isoformat()
    _save_repos_meta(meta, workspace)
