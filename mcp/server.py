#!/usr/bin/env python3
import os
import subprocess
import threading

import httpx
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient

OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL  = os.environ.get("QDRANT_URL", "http://qdrant:6333")
EMBED_MODEL = "nomic-embed-text"
HOST        = os.environ.get("MCP_HOST", "0.0.0.0")
PORT        = int(os.environ.get("MCP_PORT", "8765"))

mcp = FastMCP("cortex", host=HOST, port=PORT)


def embed(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:4000]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def warmup():
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": "warmup"},
            timeout=20,
        )
    except Exception:
        pass


@mcp.tool()
def search_notes(query: str, limit: int = 5) -> str:
    """Semantic search over Obsidian notes. Returns sections with file path, heading, and tags."""
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    results = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found."
    parts = []
    for r in results:
        p = r.payload
        tags = p.get("tags", [])
        tag_str = f" `{'`, `'.join(tags)}`" if tags else ""
        parts.append(
            f"**{p['file']} › {p['heading']}** (score: {round(r.score, 3)}){tag_str}\n\n{p['text']}"
        )
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def search_code(query: str, limit: int = 5) -> str:
    """Semantic search over source code repos (weakness-dex, mtgdle, tower-of-evolon, svelte-radio). Returns chunks with GitHub links."""
    client = QdrantClient(url=QDRANT_URL)
    vector = embed(query)
    results = client.query_points("code", query=vector, limit=limit, with_payload=True).points
    if not results:
        return "No results found."
    parts = []
    for r in results:
        p = r.payload
        header = (
            f"**{p['repo']}/{p['file']}** "
            f"lines {p['start_line']}-{p['end_line']} "
            f"({p.get('language', '')}) — score: {round(r.score, 3)}"
        )
        url = p.get("github_url", "")
        parts.append(f"{header}\n{url}\n\n{p['text']}" if url else f"{header}\n\n{p['text']}")
    return "\n\n---\n\n".join(parts)


@mcp.tool()
def reindex(notes: bool = True, code: bool = True) -> str:
    """Re-index Obsidian notes and/or source code into Qdrant. Takes a few minutes."""
    parts = []
    if notes:
        r = subprocess.run(
            ["python3", "/app/index.py"],
            capture_output=True, text=True, timeout=300,
        )
        parts.append(f"=== Notes ===\n{r.stdout}{r.stderr}".strip())
    if code:
        r = subprocess.run(
            ["python3", "/app/index_code.py"],
            capture_output=True, text=True, timeout=600,
        )
        parts.append(f"=== Code ===\n{r.stdout}{r.stderr}".strip())
    return "\n\n".join(parts) or "Nothing to index."


if __name__ == "__main__":
    threading.Thread(target=warmup, daemon=True).start()
    mcp.run(transport="sse")
