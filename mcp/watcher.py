#!/usr/bin/env python3
"""Filesystem watcher for automatic notes reindexing on .md file changes."""

import logging
import os
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import NOTES_PATH, WATCH_DEBOUNCE
from reindex import _enqueue

log = logging.getLogger("cortex")


class _NotesHandler(FileSystemEventHandler):
    """Debounced watchdog handler that triggers a notes reindex on any .md change.

    Multiple rapid file changes are collapsed into a single reindex job by
    resetting the debounce timer on each event.
    """

    def __init__(self):
        self._timer = None

    def on_any_event(self, event):
        """Schedule a debounced reindex when a .md file changes."""
        if event.is_directory or not str(event.src_path).endswith(".md"):
            return
        log.info("[watcher] change: %s — debouncing %ds", event.src_path, WATCH_DEBOUNCE)
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(WATCH_DEBOUNCE, self._on_debounce)
        self._timer.daemon = True
        self._timer.start()

    def _on_debounce(self):
        """Fire the notes reindex job after the debounce window has elapsed."""
        log.info("[watcher] debounce elapsed — queuing notes reindex")
        _enqueue(notes=True, code=False)


def _start_watcher() -> None:
    """Start the watchdog observer on NOTES_PATH; no-op if the path doesn't exist."""
    if not os.path.isdir(NOTES_PATH):
        log.warning("[watcher] notes path %s not found, skipping", NOTES_PATH)
        return
    observer = Observer()
    observer.schedule(_NotesHandler(), NOTES_PATH, recursive=True)
    observer.start()
    log.info("[watcher] watching %s for .md changes (debounce %ds)", NOTES_PATH, WATCH_DEBOUNCE)
