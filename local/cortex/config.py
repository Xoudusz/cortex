"""Paths and constants for cortex local mode."""

import os
import shutil
import tomllib
from pathlib import Path

CORTEX_DIR = Path.home() / ".cortex"
WORKSPACES_DIR = CORTEX_DIR / "workspaces"
ACTIVE_WORKSPACE_FILE = CORTEX_DIR / "active_workspace"
CONFIG_FILE = CORTEX_DIR / "config.toml"

_CONFIG_DEFAULTS: dict = {
    "watch": {"enabled": True, "debounce_seconds": 2.0},
    "index": {"last_path": "", "exclude_patterns": []},
}
_config_cache: dict | None = None

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


def get_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    cfg: dict = {k: dict(v) for k, v in _CONFIG_DEFAULTS.items()}
    if CONFIG_FILE.exists():
        try:
            loaded = tomllib.loads(CONFIG_FILE.read_text())
            for section, vals in loaded.items():
                if section in cfg and isinstance(vals, dict):
                    cfg[section].update(vals)
        except Exception:
            pass
    _config_cache = cfg
    return cfg


def save_last_indexed_path(path: str) -> None:
    global _config_cache
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if CONFIG_FILE.exists():
            text = CONFIG_FILE.read_text()
            import re
            text = re.sub(r'^last_path\s*=.*$', f'last_path = "{path}"', text, flags=re.MULTILINE)
            if 'last_path' not in text:
                text += f'\n[index]\nlast_path = "{path}"\n'
        else:
            text = f'[watch]\nenabled = true\ndebounce_seconds = 2.0\n\n[index]\nlast_path = "{path}"\nexclude_patterns = []\n'
        CONFIG_FILE.write_text(text)
    except Exception:
        pass
    _config_cache = None  # invalidate cache


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
