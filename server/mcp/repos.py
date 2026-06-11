#!/usr/bin/env python3
"""Repo registry persistence for cortex-mcp."""

import json
import os
from datetime import datetime, timezone

from config import REPOS_CONFIG, DATA_DIR, WORKSPACE

DEFAULT_REPOS = [
    "Xoudusz/weakness-dex",
    "Xoudusz/mtgdle",
    "Xoudusz/tower-of-evolon",
    "Xoudusz/tower-of-evolon-backend",
    "Xoudusz/svelte-radio",
    "Xoudusz/cortex",
    "Xoudusz/riftracoons-web",
]


def _repos_config_path(workspace: str = "") -> str:
    ws = workspace or WORKSPACE
    if ws == "default":
        return REPOS_CONFIG
    return str(DATA_DIR / ws / "repos.json")


def _load_repos_meta(workspace: str = "") -> dict:
    """Load repo metadata (repo list + indexed_at timestamps) from disk."""
    path = _repos_config_path(workspace)
    try:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"repos": data.get("repos", []), "indexed_at": data.get("indexed_at", {})}
            if isinstance(data, list) and data:
                return {"repos": data, "indexed_at": {}}
    except Exception:
        pass
    return {"repos": list(DEFAULT_REPOS), "indexed_at": {}}


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


def _update_indexed_at(repo_name: str, workspace: str = "") -> None:
    """Record the current UTC time as the last successful index time for repo_name."""
    meta = _load_repos_meta(workspace)
    meta.setdefault("indexed_at", {})[repo_name] = datetime.now(timezone.utc).isoformat()
    _save_repos_meta(meta, workspace)
