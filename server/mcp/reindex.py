#!/usr/bin/env python3
"""Job queue and reindex execution for cortex-mcp."""

import logging
import os
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone

from state import _invalidate_graph_cache, _reindex_log, _stats, get_active_workspace, _workspace_data_dir
from repos import _load_repos, _update_indexed_at, _repos_config_path
from config import DATA_DIR

log = logging.getLogger("cortex")

_job_queue: deque = deque()
_job_lock = threading.Lock()
_worker_event = threading.Event()
_reindex_state: dict = {
    "running": False, "started_at": None, "finished_at": None, "output": [],
    "error": None, "done": False, "queue_depth": 0, "current_job": None,
    "notes_finished_at": 0,
}


def _workspace_env() -> dict:
    ws = get_active_workspace()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if ws != "default":
        ws_data = str(_workspace_data_dir(ws))
        env["CORTEX_WORKSPACE"] = ws
        env["DATA_DIR"] = ws_data
        env["REPOS_CONFIG"] = _repos_config_path(ws)
    return env


def _stream(cmd: list, label: str, timeout: int) -> None:
    """Run cmd as a subprocess, streaming each output line into the reindex log."""
    env = _workspace_env()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        for line in proc.stdout:
            line = line.rstrip()
            _reindex_state["output"].append(f"[{label}] {line}")
            log.info("[%s] %s", label, line)
            if label == "notes":
                m = re.search(r"(\d+)/\d+ files cached", line)
                if m:
                    _stats["embed_cache_notes"] += int(m.group(1))
            elif label == "code":
                m = re.search(r"\((\d+) cached\)", line)
                if m:
                    _stats["embed_cache_code"] += int(m.group(1))
    finally:
        proc.wait(timeout=timeout)


def clear_cache(all_workspaces: bool = False) -> int:
    """Delete embed_cache.json for current workspace (or all if all_workspaces=True).

    Returns number of cache files deleted.
    """
    deleted = 0
    if all_workspaces:
        targets = [DATA_DIR / "embed_cache.json"] + list(DATA_DIR.glob("*/embed_cache.json"))
    else:
        ws = get_active_workspace()
        targets = [_workspace_data_dir(ws) / "embed_cache.json"]
    for f in targets:
        if f.exists():
            f.unlink()
            deleted += 1
            log.info("cleared cache: %s", f)
    return deleted


def _run_reindex(notes: bool, code: bool, repo: str = "", files=None, removed=None, force: bool = False) -> None:
    """Execute a reindex job synchronously, updating _reindex_state throughout.

    Runs /app/index.py for notes and /app/index_code.py for code.
    Increments _stats["reindex_count"] on completion regardless of errors.
    """
    if force:
        n = clear_cache(all_workspaces=False)
        log.info("force reindex: cleared %d cache file(s)", n)
    mode = "incremental" if files is not None else "full"
    _reindex_state.update(
        running=True, started_at=time.time(), finished_at=None,
        output=[], error=None, done=False,
        current_job={"notes": notes, "code": code, "repo": repo, "mode": mode, "force": force},
    )
    log.info("reindex started (notes=%s code=%s repo=%s mode=%s)", notes, code, repo or "all", mode)
    try:
        if notes:
            _stream(["/app/index.py"], "notes", 300)
            _reindex_state["notes_finished_at"] = time.time()
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
        t = time.time()
        elapsed = t - _reindex_state["started_at"]
        _reindex_state.update(running=False, done=True, finished_at=t, current_job=None)
        _stats["reindex_count"] += 1
        log.info("reindex finished in %.0fs", elapsed)


def _enqueue(notes: bool, code: bool, repo: str = "", files=None, removed=None, force: bool = False, _log_entry=None) -> str:
    """Add a reindex job to the queue and signal the worker.

    Coalesces incremental code jobs for the same repo: if a matching queued job
    already exists, the file lists are merged instead of adding a duplicate entry.
    Returns 'merged' if coalesced, 'triggered' otherwise.
    """
    with _job_lock:
        if files is not None and code:
            for job in _job_queue:
                if job.get("code") and job.get("repo") == repo and job.get("files") is not None:
                    job["files"] = list(set(job["files"] + files))
                    job["removed"] = list(set(job.get("removed", []) + (removed or [])))
                    log.info("[queue] merged %d files into queued job for %s", len(files), repo)
                    return "merged"
        _job_queue.append({"notes": notes, "code": code, "repo": repo, "files": files, "removed": removed or [], "force": force, "_log_entry": _log_entry})
        _reindex_state["queue_depth"] = len(_job_queue)
    _worker_event.set()
    return "triggered"


def _reindex_worker() -> None:
    """Background thread: drain the job queue, running one reindex at a time."""
    while True:
        _worker_event.wait()
        _worker_event.clear()
        while True:
            with _job_lock:
                if not _job_queue:
                    break
                job = _job_queue.popleft()
                _reindex_state["queue_depth"] = len(_job_queue)
            _run_reindex(job["notes"], job["code"], job.get("repo", ""), job.get("files"), job.get("removed", []), job.get("force", False))
            entry = job.get("_log_entry")
            if entry:
                entry["status"] = "failed" if _reindex_state.get("error") else "done"
            label = []
            if job["notes"]: label.append("Notes")
            if job["code"]: label.append("Code" + (f" ({job['repo']})" if job.get("repo") else ""))
            _reindex_log.insert(0, {
                "type": " + ".join(label) or "?",
                "mode": "incremental" if job.get("files") is not None else "full",
                "ts": datetime.now(timezone.utc).isoformat(),
                "duration": round((_reindex_state.get("finished_at") or 0) - (_reindex_state.get("started_at") or 0), 1),
                "status": "failed" if _reindex_state.get("error") else "done",
                "error": _reindex_state.get("error"),
            })
            _reindex_log[:] = _reindex_log[:50]


def get_status() -> dict:
    """Return a snapshot of current reindex state (safe copy for callers)."""
    return dict(_reindex_state)


def get_queue_snapshot() -> list:
    """Return a serializable snapshot of queued jobs; acquires _job_lock internally."""
    with _job_lock:
        return [{"notes": j["notes"], "code": j["code"], "repo": j.get("repo", "")}
                for j in _job_queue]
