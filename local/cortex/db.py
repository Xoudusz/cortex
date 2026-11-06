"""Shared embedded-Qdrant client for the active workspace.

Embedded Qdrant holds an exclusive file lock per storage folder, so a process must use one
client per workspace. The MCP server searches while the watcher / reindex() thread writes;
every client call is serialized through one lock (local mode is not thread-safe), and whole
index runs are serialized through `index_lock`.
"""

import atexit
import logging
import threading

from qdrant_client import QdrantClient

from .config import data_dir, ensure_index_schema, get_active_workspace, migrate_legacy, qdrant_path

log = logging.getLogger("cortex.db")

_lock = threading.RLock()
index_lock = threading.Lock()
_client: QdrantClient | None = None
_client_ws: str | None = None


class _Serialized:
    """Proxy that runs every client method under the shared lock."""

    def __init__(self, client: QdrantClient):
        self._client = client

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            with _lock:
                return attr(*args, **kwargs)
        return call


def client() -> _Serialized:
    """Client for the active workspace; reopened when the workspace changes."""
    global _client, _client_ws
    with _lock:
        ws = get_active_workspace()
        if _client is None or ws != _client_ws:
            reset()
            migrate_legacy()
            ensure_index_schema(ws)
            data_dir(ws).mkdir(parents=True, exist_ok=True)
            try:
                _client = QdrantClient(path=qdrant_path(ws))
            except Exception as e:
                if "already" in str(e).lower() or "lock" in str(e).lower():
                    raise SystemExit(
                        "Error: Qdrant database is locked by another process (cortex serve is running).\n"
                        "Stop cortex serve first, or use the reindex() MCP tool from Claude Code instead."
                    ) from e
                raise
            _client_ws = ws
            log.info("opened index for workspace '%s'", ws)
        return _Serialized(_client)


def reset() -> None:
    """Close the current client (workspace switch, shutdown)."""
    global _client, _client_ws
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
        _client = None
        _client_ws = None


atexit.register(reset)
