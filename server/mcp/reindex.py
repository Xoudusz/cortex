#!/usr/bin/env python3
"""Job queue and reindex execution for cortex-mcp."""

import base64
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import users as _users
from state import (_invalidate_graph_cache, _reindex_log, _stats, bind_workspace, get_active_workspace,
                   unbind_workspace, _workspace_data_dir)
from repos import _load_repos, _record_index_result, _repos_config_path
from config import DATA_DIR, get_github_token

log = logging.getLogger("cortex")

_job_queue: deque = deque()
_job_lock = threading.Lock()
_worker_event = threading.Event()
_reindex_state: dict = {
    "running": False, "started_at": None, "finished_at": None, "output": [],
    "error": None, "done": False, "queue_depth": 0, "current_job": None,
    "notes_finished_at": 0,
}


def _workspace_env(notes_path: str = "") -> dict:
    ws = get_active_workspace()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    token, _ = get_github_token()
    if token:
        env["GITHUB_TOKEN"] = token
    if ws != "default":
        ws_data = str(_workspace_data_dir(ws))
        env["CORTEX_WORKSPACE"] = ws
        env["DATA_DIR"] = ws_data
        env["REPOS_CONFIG"] = _repos_config_path(ws)
    if notes_path:
        env["NOTES_PATH"] = notes_path
    return env


def _out(label: str, line: str) -> None:
    _reindex_state["output"].append(f"[{label}] {line}")
    log.info("[%s] %s", label, line)


def _git_auth_args(token: str) -> list:
    """Per-command GitHub auth header: the token is never written into .git/config or the URL."""
    if not token:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]


def _sync_wiki(ws: str, repo: str) -> Path | None:
    """Clone or update the workspace's wiki repo (markdown notes) into <ws data>/wiki. None on failure."""
    dest = _workspace_data_dir(ws) / "wiki"
    url = f"https://github.com/{repo}.git"
    token, _ = get_github_token()
    auth = _git_auth_args(token)
    if dest.exists():
        cur = subprocess.run(["git", "-C", str(dest), "remote", "get-url", "origin"],
                             capture_output=True, text=True).stdout.strip()
        if cur != url:  # wiki repo was changed: start over
            shutil.rmtree(dest, ignore_errors=True)
    if dest.exists():
        _out("wiki", f"updating {repo}...")
        steps = [["git", *auth, "-C", str(dest), "fetch", "--depth=1", "origin"],
                 ["git", "-C", str(dest), "reset", "--hard", "FETCH_HEAD"]]
    else:
        _out("wiki", f"cloning {repo} (shallow)...")
        dest.parent.mkdir(parents=True, exist_ok=True)
        steps = [["git", *auth, "clone", "--depth=1", url, str(dest)]]
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            err = " | ".join(l.strip() for l in r.stderr.splitlines() if l.strip())[-400:]
            if token:
                err = err.replace(token, "***")
            _out("wiki", f"SKIP {repo}: {err or 'git failed'}")
            return None
    return dest


def _stream(cmd: list, label: str, timeout: int, notes_path: str = "") -> None:
    """Run cmd as a subprocess, streaming each output line into the reindex log."""
    env = _workspace_env(notes_path)
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
    ws = get_active_workspace()
    _reindex_state.update(
        running=True, started_at=time.time(), finished_at=None,
        output=[], error=None, done=False, last_ws=ws,
        current_job={"notes": notes, "code": code, "repo": repo, "mode": mode, "force": force, "ws": ws},
    )
    log.info("reindex started (ws=%s notes=%s code=%s repo=%s mode=%s)", ws, notes, code, repo or "all", mode)
    try:
        if notes:
            if ws == "default":
                _stream(["/app/index.py"], "notes", 300)
            else:
                # Shared workspaces never read the admin's vault (NOTES_PATH): only their own wiki repo.
                wiki = _users.get_wiki(ws)
                path = _sync_wiki(ws, wiki) if wiki else None
                if path:
                    _stream(["/app/index.py"], "notes", 300, notes_path=str(path))
                elif not wiki:
                    _out("notes", f"skipped: workspace '{ws}' has no wiki repo (set_workspace_wiki)")
            _reindex_state["notes_finished_at"] = time.time()
        if code:
            cmd = ["/app/index_code.py"]
            if repo:
                cmd += ["--repo", repo]
            if files is not None:
                cmd += ["--files"] + files
            if removed:
                cmd += ["--remove-files"] + removed
            first_line = len(_reindex_state["output"])
            _stream(cmd, "code", 600)
            _invalidate_graph_cache(repo)
            # index_code prints "SKIP owner/name: <reason>" for repos it could not clone/pull
            failed = {}
            for line in _reindex_state["output"][first_line:]:
                m = re.search(r"SKIP ([^/\s]+)/([^:\s]+): (.*)", line)
                if m:
                    failed[m.group(2)] = m.group(3)
            names = [repo] if repo else [r.split("/")[1] for r in _load_repos()]
            for name in names:
                _record_index_result(name, failed.get(name))
    except Exception as e:
        _reindex_state["error"] = str(e)
        log.error("reindex error: %s", e)
    finally:
        t = time.time()
        elapsed = t - _reindex_state["started_at"]
        _reindex_state.update(running=False, done=True, finished_at=t, current_job=None)
        _stats["reindex_count"] += 1
        log.info("reindex finished in %.0fs", elapsed)


def _enqueue(notes: bool, code: bool, repo: str = "", files=None, removed=None, force: bool = False, _log_entry=None,
             workspace: str = "") -> str:
    """Add a reindex job to the queue and signal the worker.

    The job runs in `workspace` (default: the caller's active workspace, captured now).
    Coalesces incremental code jobs for the same repo + workspace: if a matching queued job
    already exists, the file lists are merged instead of adding a duplicate entry.
    Returns 'merged' if coalesced, 'triggered' otherwise.
    """
    ws = workspace or get_active_workspace()
    with _job_lock:
        if files is not None and code:
            for job in _job_queue:
                if job.get("code") and job.get("repo") == repo and job.get("files") is not None \
                        and job.get("ws") == ws:
                    job["files"] = list(set(job["files"] + files))
                    job["removed"] = list(set(job.get("removed", []) + (removed or [])))
                    log.info("[queue] merged %d files into queued job for %s", len(files), repo)
                    return "merged"
        _job_queue.append({"notes": notes, "code": code, "repo": repo, "files": files, "removed": removed or [],
                           "force": force, "_log_entry": _log_entry, "ws": ws})
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
            ws_token = bind_workspace(job.get("ws") or "default")
            try:
                _run_reindex(job["notes"], job["code"], job.get("repo", ""), job.get("files"), job.get("removed", []),
                             job.get("force", False))
            finally:
                unbind_workspace(ws_token)
            entry = job.get("_log_entry")
            if entry:
                entry["status"] = "failed" if _reindex_state.get("error") else "done"
            label = []
            if job["notes"]: label.append("Notes")
            if job["code"]: label.append("Code" + (f" ({job['repo']})" if job.get("repo") else ""))
            _reindex_log.insert(0, {
                "ws": job.get("ws") or "default",
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
        return [{"notes": j["notes"], "code": j["code"], "repo": j.get("repo", ""), "ws": j.get("ws", "default")}
                for j in _job_queue]
