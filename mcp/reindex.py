#!/usr/bin/env python3
"""Job queue and reindex execution for cortex-mcp."""

import logging
import subprocess
import threading
import time
from collections import deque

from config import _invalidate_graph_cache, _load_repos, _update_indexed_at, _stats

log = logging.getLogger("cortex")

_job_queue: deque = deque()
_job_lock = threading.Lock()
_worker_event = threading.Event()
_reindex_state: dict = {
    "running": False, "started_at": None, "output": [],
    "error": None, "done": False, "queue_depth": 0,
}


def _stream(cmd: list, label: str, timeout: int) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in proc.stdout:
            line = line.rstrip()
            _reindex_state["output"].append(f"[{label}] {line}")
            log.info("[%s] %s", label, line)
    finally:
        proc.wait(timeout=timeout)


def _run_reindex(notes: bool, code: bool, repo: str = "", files=None, removed=None) -> None:
    _reindex_state.update(running=True, started_at=time.time(), output=[], error=None, done=False)
    mode = "incremental" if files is not None else "full"
    log.info("reindex started (notes=%s code=%s repo=%s mode=%s)", notes, code, repo or "all", mode)
    try:
        if notes:
            _stream(["/app/index.py"], "notes", 300)
        if code:
            cmd = ["/app/index_code.py"]
            if repo:
                cmd += ["--repo", repo]
            if files is not None:
                cmd += ["--files"] + files
            if removed:
                cmd += ["--remove-files"] + removed
            _stream(cmd, "code", 600)
            _invalidate_graph_cache(repo)
            if repo:
                _update_indexed_at(repo)
            else:
                for r in _load_repos():
                    _update_indexed_at(r.split("/")[1])
    except Exception as e:
        _reindex_state["error"] = str(e)
        log.error("reindex error: %s", e)
    finally:
        elapsed = time.time() - _reindex_state["started_at"]
        _reindex_state.update(running=False, done=True)
        log.info("reindex finished in %.0fs", elapsed)


def _enqueue(notes: bool, code: bool, repo: str = "", files=None, removed=None) -> None:
    with _job_lock:
        if files is not None and code:
            for job in _job_queue:
                if job.get("code") and job.get("repo") == repo and job.get("files") is not None:
                    job["files"] = list(set(job["files"] + files))
                    job["removed"] = list(set(job.get("removed", []) + (removed or [])))
                    log.info("[queue] merged %d files into queued job for %s", len(files), repo)
                    return
        _job_queue.append({"notes": notes, "code": code, "repo": repo, "files": files, "removed": removed or []})
        _reindex_state["queue_depth"] = len(_job_queue)
    _worker_event.set()


def _reindex_worker() -> None:
    while True:
        _worker_event.wait()
        _worker_event.clear()
        while True:
            with _job_lock:
                if not _job_queue:
                    break
                job = _job_queue.popleft()
                _reindex_state["queue_depth"] = len(_job_queue)
            _run_reindex(job["notes"], job["code"], job.get("repo", ""), job.get("files"), job.get("removed", []))
