#!/usr/bin/env python3
"""Mtime-based embedding cache — skip re-embedding unchanged files on full reindex."""

import json
import os
from pathlib import Path


def _default_cache_file() -> Path:
    repos_config = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
    return Path(repos_config).parent / "embed_cache.json"


def load_cache(section: str, cache_file: Path | None = None) -> dict:
    """Load {rel_path: {"mtime": float, "hash": str}} for given section ('notes' or 'code')."""
    if cache_file is None:
        cache_file = _default_cache_file()
    try:
        if cache_file.exists():
            raw = json.loads(cache_file.read_text()).get(section, {})
            return {k: v if isinstance(v, dict) else {"mtime": v, "hash": ""} for k, v in raw.items()}
    except Exception:
        pass
    return {}


def save_cache(section: str, data: dict, cache_file: Path | None = None) -> None:
    """Persist updated cache section without touching other sections."""
    if cache_file is None:
        cache_file = _default_cache_file()
    try:
        existing = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        existing[section] = data
        cache_file.write_text(json.dumps(existing))
    except Exception as e:
        print(f"warn: cache save failed: {e}", flush=True)
