#!/usr/bin/env python3
"""Environment variables, constants, and embedding utilities for cortex-mcp."""

import logging
import os
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cortex")

OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL     = os.environ.get("QDRANT_URL", "http://qdrant:6333")
EMBED_MODEL    = "nomic-embed-text"
HOST           = os.environ.get("MCP_HOST", "0.0.0.0")
PORT           = int(os.environ.get("MCP_PORT", "8765"))
NOTES_PATH     = os.environ.get("NOTES_PATH", "/notes")
WATCH_DEBOUNCE = int(os.environ.get("WATCH_DEBOUNCE", "60"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BASE_URL       = os.environ.get("BASE_URL", "http://localhost:8765").rstrip("/")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
REPOS_CONFIG   = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
DATA_DIR       = Path(REPOS_CONFIG).parent
VERSION        = (Path("/app/VERSION").read_text().strip()
                  if Path("/app/VERSION").exists() else "dev")
STATS_FILE     = DATA_DIR / "stats.json"


def embed(text: str) -> list:
    """Embed text using the Ollama nomic-embed-text model; truncates to 4000 chars."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:4000]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def warmup() -> None:
    """Send a dummy embedding request to pre-load the model into Ollama's memory."""
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": "warmup"},
            timeout=20,
        )
        log.info("warmup OK")
    except Exception as e:
        log.warning("warmup failed: %s", e)
