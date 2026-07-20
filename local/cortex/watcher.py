"""Debounced filesystem watcher for automatic reindex on file changes."""

import threading
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler as _Handler

    class CortexWatcher:
        def __init__(self, path: Path, debounce: float = 2.0):
            self._path = path
            self._debounce = debounce
            self._timer: threading.Timer | None = None
            self._lock = threading.Lock()
            self._observer = Observer()

        def _schedule(self):
            with self._lock:
                if self._timer:
                    self._timer.cancel()
                self._timer = threading.Timer(self._debounce, self._fire)
                self._timer.daemon = True
                self._timer.start()

        def _fire(self):
            with self._lock:
                self._timer = None
            try:
                from .indexer import index_path
                index_path(self._path)
            except Exception as e:
                print(f"[watcher] reindex failed: {e}", flush=True)

        def start(self):
            handler = type("_H", (_Handler,), {
                "on_any_event": lambda s, e: (
                    None if e.is_directory or not str(e.src_path).endswith(".md")
                    else self._schedule()
                ),
            })()
            self._observer.schedule(handler, str(self._path), recursive=True)
            self._observer.daemon = True
            self._observer.start()
            print(f"[cortex] watching {self._path} (debounce {self._debounce}s)", flush=True)

        def stop(self):
            self._observer.stop()
            self._observer.join()

except ImportError:
    class CortexWatcher:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            print("[cortex] watchdog not installed — auto-reindex disabled", flush=True)

        def stop(self):
            pass
