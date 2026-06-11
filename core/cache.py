#!/usr/bin/env python3
"""Mtime-based embedding cache — skip re-embedding unchanged files on full reindex."""

import json
from pathlib import Path


def load_cache(section: str, cache_file: Path) -> dict:
    """Load {rel_path: mtime} for given section ('notes' or 'code')."""
    try:
        if cache_file.exists():
            return json.loads(cache_file.read_text()).get(section, {})
    except Exception:
        pass
    return {}


def save_cache(section: str, data: dict, cache_file: Path) -> None:
    """Persist updated cache section without touching other sections."""
    try:
        existing = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        existing[section] = data
        cache_file.write_text(json.dumps(existing))
    except Exception as e:
        print(f"warn: cache save failed: {e}", flush=True)
