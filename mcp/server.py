#!/usr/bin/env python3
import logging
import os
import subprocess
import threading
import time

import httpx
from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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
        log.info("warmup OK")
    except Exception as e:
        log.warning("warmup failed: %s", e)


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


def _stream(cmd: list[str], label: str, timeout: int) -> None:
    """Run cmd, streaming each output line to logger and _reindex_state."""
    _reindex_state["output"].append(f"=== {label}: starting ===")
    log.info("[%s] starting", label)
    proc = subprocess.Popen(
        ["python3", "-u"] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        for raw in proc.stdout:
            line = raw.rstrip()
            if line:
                log.info("[%s] %s", label, line)
                _reindex_state["output"].append(line)
        proc.wait()
    finally:
        timer.cancel()
    if proc.returncode not in (0, None):
        msg = f"=== {label}: exited {proc.returncode} ==="
        log.warning(msg)
        _reindex_state["output"].append(msg)
    else:
        log.info("[%s] done", label)


def _run_reindex(notes: bool, code: bool) -> None:
    _reindex_state.update(running=True, started_at=time.time(), output=[], error=None, done=False)
    log.info("reindex started (notes=%s code=%s)", notes, code)
    try:
        if notes:
            _stream(["/app/index.py"], "notes", 300)
        if code:
            _stream(["/app/index_code.py"], "code", 600)
    except Exception as e:
        _reindex_state["error"] = str(e)
        log.error("reindex error: %s", e)
    finally:
        elapsed = time.time() - _reindex_state["started_at"]
        _reindex_state.update(running=False, done=True)
        log.info("reindex finished in %.0fs", elapsed)


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


class _NotesHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer: threading.Timer | None = None

    def on_any_event(self, event):
        if event.is_directory or not str(event.src_path).endswith(".md"):
            return
        log.info("[watcher] change: %s — debouncing %ds", event.src_path, WATCH_DEBOUNCE)
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(WATCH_DEBOUNCE, self._trigger)
        self._timer.daemon = True
        self._timer.start()

    def _trigger(self):
        with _reindex_lock:
            if _reindex_state["running"]:
                log.info("[watcher] reindex already running, skipping")
                return
            log.info("[watcher] debounce elapsed — triggering notes reindex")
            threading.Thread(target=_run_reindex, args=(True, False), daemon=True).start()


def _start_watcher():
    if not os.path.isdir(NOTES_PATH):
        log.warning("[watcher] notes path %s not found, skipping", NOTES_PATH)
        return
    observer = Observer()
    observer.schedule(_NotesHandler(), NOTES_PATH, recursive=True)
    observer.start()
    log.info("[watcher] watching %s for .md changes (debounce %ds)", NOTES_PATH, WATCH_DEBOUNCE)


if __name__ == "__main__":
    threading.Thread(target=warmup, daemon=True).start()
    threading.Thread(target=_start_watcher, daemon=True).start()
    mcp.run(transport="sse")
