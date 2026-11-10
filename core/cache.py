#!/usr/bin/env python3
"""Mtime-based embedding cache — skip re-embedding unchanged files on full reindex."""

import logging
import json
import os
import tempfile
from pathlib import Path

log = logging.getLogger("cortex.cache")


def _default_cache_file() -> Path:
    repos_config = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
    return Path(repos_config).parent / "embed_cache.json"


def load_cache(section: str, cache_file: Path | None = None) -> dict:
    """Load {rel_path: {"mtime": float, "hash": str}} for given section ('notes' or 'code')."""
    if cache_file is None:
        cache_file = _default_cache_file()
    if not cache_file.exists():
        return {}
    try:
        raw = json.loads(cache_file.read_text()).get(section, {})
        return {k: v if isinstance(v, dict) else {"mtime": v, "hash": ""} for k, v in raw.items()}
    except Exception as e:
        log.warning(f"embed cache unreadable at {cache_file} ({e}); all files will be re-embedded")
        return {}


def save_cache(section: str, data: dict, cache_file: Path | None = None) -> None:
    """Persist updated cache section without touching other sections. Written atomically."""
    if cache_file is None:
        cache_file = _default_cache_file()
    tmp_name = None
    try:
        try:
            existing = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        except ValueError:
            existing = {}  # corrupt file: load_cache already warned; overwrite with a valid one
        if not isinstance(existing, dict):
            existing = {}  # valid JSON but not an object (e.g. []): same recovery
        existing[section] = data
        fd, tmp_name = tempfile.mkstemp(dir=cache_file.parent, prefix=cache_file.name + ".", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(existing))
        os.replace(tmp_name, cache_file)
    except Exception as e:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)
        log.warning(f"warn: cache save failed: {e}")
