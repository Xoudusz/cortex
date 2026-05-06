#!/usr/bin/env python3
import os
import subprocess
import threading
import time

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


_reindex_lock = threading.Lock()
_reindex_state: dict = {"running": False, "started_at": None, "output": [], "error": None, "done": False}


def _run_reindex(notes: bool, code: bool) -> None:
    _reindex_state.update(running=True, started_at=time.time(), output=[], error=None, done=False)
    try:
        if notes:
            _reindex_state["output"].append("=== Notes: starting ===")
            r = subprocess.run(["python3", "/app/index.py"], capture_output=True, text=True, timeout=300)
            _reindex_state["output"].append(f"=== Notes ===\n{r.stdout}{r.stderr}".strip())
        if code:
            _reindex_state["output"].append("=== Code: starting ===")
            r = subprocess.run(["python3", "/app/index_code.py"], capture_output=True, text=True, timeout=600)
            _reindex_state["output"].append(f"=== Code ===\n{r.stdout}{r.stderr}".strip())
    except Exception as e:
        _reindex_state["error"] = str(e)
    finally:
        _reindex_state.update(running=False, done=True)


@mcp.tool()
def reindex(notes: bool = True, code: bool = True) -> str:
    """Start async re-indexing of Obsidian notes and/or source code into Qdrant. Returns immediately; use reindex_status() to check progress."""
    with _reindex_lock:
        if _reindex_state["running"]:
            return "Reindex already in progress. Use reindex_status() to check."
        threading.Thread(target=_run_reindex, args=(notes, code), daemon=True).start()
    return "Reindex started in background. Use reindex_status() to check progress."


@mcp.tool()
def reindex_status() -> str:
    """Check status of the last reindex operation."""
    s = _reindex_state
    if s["started_at"] is None:
        return "No reindex has been run yet."
    elapsed = time.time() - s["started_at"]
    status = "running" if s["running"] else "done"
    lines = [f"Status: {status} ({elapsed:.0f}s elapsed)"]
    if s["output"]:
        lines.append("\n".join(s["output"]))
    if s["error"]:
        lines.append(f"Error: {s['error']}")
    return "\n\n".join(lines)


if __name__ == "__main__":
    threading.Thread(target=warmup, daemon=True).start()
    mcp.run(transport="sse")
