"""Paths and constants for cortex local mode."""

import os
import shutil
from pathlib import Path

CORTEX_DIR = Path.home() / ".cortex"
WORKSPACES_DIR = CORTEX_DIR / "workspaces"
ACTIVE_WORKSPACE_FILE = CORTEX_DIR / "active_workspace"

EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VECTOR_SIZE = 768
PPR_THRESHOLD = float(os.environ.get("PPR_THRESHOLD", "0.03"))

try:
    from importlib.metadata import version
    VERSION = version("cortex-local")
except Exception:
    VERSION = "dev"


def get_active_workspace() -> str:
    if ACTIVE_WORKSPACE_FILE.exists():
        return ACTIVE_WORKSPACE_FILE.read_text().strip() or "default"
    return "default"


def set_active_workspace(name: str) -> None:
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_WORKSPACE_FILE.write_text(name)


def get_workspace_dir(name: str | None = None) -> Path:
    return WORKSPACES_DIR / (name or get_active_workspace())


def qdrant_path(ws: str | None = None) -> str:
    return str(get_workspace_dir(ws) / "qdrant")


def data_dir(ws: str | None = None) -> Path:
    return get_workspace_dir(ws)


def cache_file(ws: str | None = None) -> Path:
    return get_workspace_dir(ws) / "embed_cache.json"


def stats_file(ws: str | None = None) -> Path:
    return get_workspace_dir(ws) / "stats.json"


def migrate_legacy() -> None:
    """Move old flat ~/.cortex/ layout into ~/.cortex/workspaces/default/ on first run."""
    old_qdrant = CORTEX_DIR / "qdrant"
    default_dir = WORKSPACES_DIR / "default"
    if not old_qdrant.exists() or WORKSPACES_DIR.exists():
        return
    default_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_qdrant), str(default_dir / "qdrant"))
    for fname in ("embed_cache.json", "stats.json"):
        src = CORTEX_DIR / fname
        if src.exists():
            shutil.move(str(src), str(default_dir / fname))
    for f in CORTEX_DIR.glob("graph_*.json"):
        shutil.move(str(f), str(default_dir / f.name))
