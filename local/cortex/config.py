"""Paths and constants for cortex local mode."""

from pathlib import Path

CORTEX_DIR = Path.home() / ".cortex"
QDRANT_PATH = str(CORTEX_DIR / "qdrant")
DATA_DIR = CORTEX_DIR
STATS_FILE = CORTEX_DIR / "stats.json"
CACHE_FILE = CORTEX_DIR / "embed_cache.json"

EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VECTOR_SIZE = 768

try:
    from importlib.metadata import version
    VERSION = version("cortex")
except Exception:
    VERSION = "dev"
