#!/usr/bin/env python3
"""Mtime-based embedding cache — skip re-embedding unchanged files on full reindex."""

import json
import os
from pathlib import Path

CACHE_FILE = Path(os.environ.get("REPOS_CONFIG", "/app/data/repos.json")).parent / "embed_cache.json"


def load_cache(section: str) -> dict:
    """Load {rel_path: mtime} for given section ('notes' or 'code')."""
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text()).get(section, {})
    except Exception:
        pass
    return {}


def save_cache(section: str, data: dict) -> None:
    """Persist updated cache section to CACHE_FILE without touching other sections."""
    try:
        existing = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
        existing[section] = data
        CACHE_FILE.write_text(json.dumps(existing))
    except Exception as e:
        print(f"warn: cache save failed: {e}", flush=True)
