"""Debounced filesystem watcher: reindex an index root shortly after its files change."""

import logging
import threading
from pathlib import Path
from typing import Callable

from .core.chunker import CODE_EXTS, SKIP_DIRS

log = logging.getLogger("cortex.watcher")

_WATCH_EXTS = set(CODE_EXTS) | {".md"}
_IGNORED_DIRS = set(SKIP_DIRS) | {".obsidian"}
_CHANGE_EVENTS = {"created", "modified", "deleted", "moved"}


def _relevant(path: str) -> bool:
    p = Path(path)
    return p.suffix in _WATCH_EXTS and not any(part in _IGNORED_DIRS for part in p.parts)


try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class CortexWatcher:
        """Watches several roots; calls on_change(root) once per root after `debounce` quiet seconds."""

        def __init__(self, roots: list, debounce: float, on_change: Callable[[Path], None]):
            self._roots = sorted((Path(r).resolve() for r in roots), key=lambda p: -len(p.parts))
            self._debounce = debounce
            self._on_change = on_change
            self._pending: set = set()
            self._timer: threading.Timer | None = None
            self._lock = threading.Lock()
            self._observer = Observer()
            self._observer.daemon = True

        def _root_of(self, path: str) -> Path | None:
            p = Path(path).resolve()
            for root in self._roots:  # deepest root wins for nested roots
                if p == root or root in p.parents:
                    return root
            return None

        def _event(self, event) -> None:
            # Only content changes. watchdog also emits opened/closed(_no_write) on Linux, and
            # the indexer reading files would otherwise retrigger itself forever.
            if event.is_directory or event.event_type not in _CHANGE_EVENTS:
                return
            for path in (event.src_path, getattr(event, "dest_path", "") or ""):
                if path and _relevant(str(path)):
                    root = self._root_of(str(path))
                    if root:
                        self._schedule(root)

        def _schedule(self, root: Path) -> None:
            with self._lock:
                self._pending.add(root)
                if self._timer:
                    self._timer.cancel()
                self._timer = threading.Timer(self._debounce, self._fire)
                self._timer.daemon = True
                self._timer.start()

        def _fire(self) -> None:
            with self._lock:
                roots, self._pending, self._timer = self._pending, set(), None
            for root in roots:
                try:
                    self._on_change(root)
                except Exception:
                    log.exception("reindex after change failed: %s", root)

        def start(self) -> None:
            outer = self

            class _Handler(FileSystemEventHandler):
                def on_any_event(self, event):
                    outer._event(event)

            handler = _Handler()
            for root in self._roots:
                self._observer.schedule(handler, str(root), recursive=True)
                log.info("watching %s (debounce %ss)", root.as_posix(), self._debounce)
            self._observer.start()

        def stop(self) -> None:
            with self._lock:
                if self._timer:
                    self._timer.cancel()
                self._timer = None
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:
                pass

except ImportError:
    class CortexWatcher:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            log.warning("watchdog not installed - auto-reindex disabled")

        def stop(self):
            pass
