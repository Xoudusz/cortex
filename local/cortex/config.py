"""Paths and constants for cortex local mode."""

import json
import os
import shutil
import tomllib
from pathlib import Path

CORTEX_DIR = Path.home() / ".cortex"
MODELS_DIR = CORTEX_DIR / "models"
WORKSPACES_DIR = CORTEX_DIR / "workspaces"
ACTIVE_WORKSPACE_FILE = CORTEX_DIR / "active_workspace"
CONFIG_FILE = CORTEX_DIR / "config.toml"

_CONFIG_DEFAULTS: dict = {
    "watch": {"enabled": True, "debounce_seconds": 2.0},
    "index": {"last_path": "", "roots": [], "exclude_patterns": []},
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


# Bump when stored payloads change incompatibly; older indexes are wiped and rebuilt.
# 2: POSIX payload paths (2.4.5 stored backslashes on Windows).
INDEX_SCHEMA = 2


def index_meta_file(ws: str | None = None) -> Path:
    return get_workspace_dir(ws) / "index_meta.json"


def read_index_meta(ws: str | None = None) -> dict:
    try:
        return json.loads(index_meta_file(ws).read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_index_meta(meta: dict, ws: str | None = None) -> None:
    f = index_meta_file(ws)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def ensure_index_schema(ws: str | None = None) -> bool:
    """Wipe an index built with an older schema. Returns True if a wipe happened.

    Must run before any QdrantClient opens the workspace.
    """
    meta = read_index_meta(ws)
    if meta.get("schema") == INDEX_SCHEMA:
        return False
    ws_dir = get_workspace_dir(ws)
    wiped = False
    qdir = ws_dir / "qdrant"
    if qdir.exists():
        shutil.rmtree(qdir, ignore_errors=True)
        wiped = True
    for f in [ws_dir / "embed_cache.json", *ws_dir.glob("graph_*.json")]:
        if f.exists():
            f.unlink()
            wiped = True
    meta["schema"] = INDEX_SCHEMA
    write_index_meta(meta, ws)
    if wiped:
        import logging
        logging.getLogger("cortex.config").warning(
            "index schema changed (now v%d): old index wiped - run: cortex index <path>", INDEX_SCHEMA)
    return wiped


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
        except Exception as e:
            import logging
            logging.getLogger("cortex.config").warning("config.toml unreadable (%s): %s", CONFIG_FILE, e)
    _config_cache = cfg
    return cfg


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    # JSON string escaping is valid TOML basic-string escaping (handles \\ and quotes).
    return json.dumps(str(v))


def save_config(cfg: dict) -> None:
    """Write config.toml from a {section: {key: value}} dict."""
    global _config_cache
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    lines: list = []
    for section, vals in cfg.items():
        if not isinstance(vals, dict):
            continue
        lines.append(f"[{section}]")
        lines.extend(f"{k} = {_toml_value(v)}" for k, v in vals.items())
        lines.append("")
    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
    _config_cache = None


def save_last_indexed_path(path: str) -> None:
    """Record PATH as last indexed and add it to index.roots (stored as POSIX)."""
    posix = Path(path).resolve().as_posix()
    cfg = {k: dict(v) for k, v in get_config().items()}
    cfg["index"]["last_path"] = posix
    roots = [r for r in cfg["index"].get("roots", []) if r != posix]
    cfg["index"]["roots"] = roots + [posix]
    save_config(cfg)


def get_roots() -> list:
    """Indexed roots that still exist (falls back to last_path for pre-2.4.6 configs)."""
    idx = get_config()["index"]
    roots = list(idx.get("roots") or [])
    if not roots and idx.get("last_path"):
        roots = [idx["last_path"]]
    return [r for r in roots if Path(r).exists()]


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
