#!/usr/bin/env python3
"""HTTP route handlers for the cortex web API."""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import DATA_DIR, GITHUB_TOKEN, OLLAMA_URL, QDRANT_URL, STATS_FILE, VERSION, WEBHOOK_SECRET, embed
from state import _reindex_log, _stats, _webhook_log
from repos import _load_repos, _load_repos_meta, _save_repos
from reindex import _enqueue, _job_lock, _job_queue, _reindex_state
from web_ui import LOGO_SVG, api_search, api_stats, api_status, ui

log = logging.getLogger("cortex")


async def health(request: Request) -> JSONResponse:
    """Liveness probe — always returns 200."""
    return JSONResponse({"status": "ok"})


async def favicon(request: Request) -> Response:
    """Serve the Cortex logo as an SVG favicon."""
    return Response(LOGO_SVG, media_type="image/svg+xml")


def _verify_webhook_sig(body: bytes, sig_header: str) -> bool:
    """Return True if the HMAC-SHA256 signature on body matches sig_header."""
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig_header, expected)


def _parse_webhook_payload(body: bytes) -> tuple[str, list, list]:
    """Extract repo name and changed/removed file lists from a GitHub push payload."""
    try:
        payload = json.loads(body)
        repo = payload.get("repository", {}).get("name", "")
        changed, removed = [], []
        for commit in payload.get("commits", []):
            changed += commit.get("added", []) + commit.get("modified", [])
            removed += commit.get("removed", [])
        removed = list(set(removed))
        changed = list(set(changed) - set(removed))
        return repo, changed, removed
    except Exception:
        return "", [], []


async def webhook(request: Request) -> JSONResponse:
    """Handle GitHub push webhooks: validate signature, enqueue incremental reindex."""
    body = await request.body()
    if WEBHOOK_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_webhook_sig(body, sig):
            log.warning("[webhook] invalid signature — rejected")
            return JSONResponse({"error": "invalid signature"}, status_code=401)
    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return JSONResponse({"status": "ignored", "event": event})
    repo, changed, removed = _parse_webhook_payload(body)
    ts = datetime.now(timezone.utc).isoformat()
    log_entry = {"repo": repo or "unknown", "ts": ts, "status": "queued", "files": len(changed)}
    _webhook_log.insert(0, log_entry)
    _webhook_log[:] = _webhook_log[:50]
    status = _enqueue(False, True, repo, files=changed or None, removed=removed, _log_entry=log_entry)
    log_entry["status"] = status
    log.info("[webhook] push on %s -> %d changed, %d removed -> %s", repo or "unknown", len(changed), len(removed), status)
    return JSONResponse({"status": "ok", "repo": repo, "files_changed": len(changed)})


async def _ui_handler(request: Request):
    """Serve the web dashboard HTML."""
    return await ui(request)


async def _api_search_handler(request: Request):
    """Proxy semantic search requests to the Qdrant-backed search handler."""
    return await api_search(request, QDRANT_URL, embed)


async def _api_status_handler(request: Request):
    """Return the current reindex job state and queue snapshot."""
    with _job_lock:
        queue_snapshot = [{"notes": j["notes"], "code": j["code"], "repo": j.get("repo", "")} for j in _job_queue]
    return await api_status(request, _reindex_state, queue_snapshot)


async def _api_reindex_handler(request: Request):
    """Enqueue a reindex job from a JSON body with notes/code/repo flags."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    _enqueue(body.get("notes", True), body.get("code", True), body.get("repo", ""), files=None)
    return JSONResponse({"status": "queued"})


async def _api_stats_handler(request: Request):
    """Return Qdrant collection counts, Ollama status, and MCP efficiency stats."""
    stats_payload = dict(_stats)
    stats_payload["version"] = VERSION
    try:
        if STATS_FILE.exists():
            all_versions = json.loads(STATS_FILE.read_text()).get("versions", {})
            stats_payload["history"] = {v: d for v, d in all_versions.items() if v != VERSION}
        else:
            stats_payload["history"] = {}
    except Exception:
        stats_payload["history"] = {}
    return await api_stats(request, QDRANT_URL, OLLAMA_URL, stats_payload)


async def _api_graph_handler(request: Request) -> JSONResponse:
    """Return the raw graph JSON for a repo. Use repo='notes' for the notes graph."""
    repo = request.path_params.get("repo", "")
    if not repo:
        return JSONResponse({"error": "repo required"}, status_code=400)
    graph_path = DATA_DIR / ("graph_notes.json" if repo == "notes" else f"graph_{repo}.json")
    if not graph_path.exists():
        return JSONResponse({"error": f"No graph for '{repo}'. Run reindex first."}, status_code=404)
    try:
        return JSONResponse(json.loads(graph_path.read_text()))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def _api_repos_handler(request: Request) -> JSONResponse:
    """GET: list tracked repos. POST: add a repo (owner/name format)."""
    if request.method == "GET":
        return JSONResponse({"repos": _load_repos()})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    repo = body.get("repo", "").strip()
    if not repo or "/" not in repo:
        return JSONResponse({"error": "Use owner/name format (e.g. Xoudusz/my-repo)"}, status_code=400)
    repos = _load_repos()
    if repo not in repos:
        repos.append(repo)
        _save_repos(repos)
    return JSONResponse({"repos": repos})


async def _api_repos_delete(request: Request) -> JSONResponse:
    """Remove a repo from the tracked list by owner/name path param."""
    repo = request.path_params.get("repo", "")
    repos = [r for r in _load_repos() if r != repo]
    _save_repos(repos)
    log.info("[repos] removed %s", repo)
    return JSONResponse({"repos": repos})


async def _api_repos_meta_handler(request: Request) -> JSONResponse:
    """Return full repo metadata including last indexed timestamps."""
    return JSONResponse(_load_repos_meta())


async def _api_github_repos(request: Request) -> JSONResponse:
    """Fetch the authenticated user's non-archived GitHub repos via the API."""
    if not GITHUB_TOKEN:
        return JSONResponse({"error": "GITHUB_TOKEN not configured"}, status_code=503)
    try:
        resp = httpx.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"},
            params={"per_page": 100, "sort": "updated", "affiliation": "owner"},
            timeout=10,
        )
        resp.raise_for_status()
        repos = [r["full_name"] for r in resp.json() if not r.get("archived")]
        return JSONResponse({"repos": repos})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def _api_webhook_log_handler(request: Request) -> JSONResponse:
    """Return the in-memory webhook event log (last 50 entries)."""
    return JSONResponse({"log": _webhook_log})


async def _api_reindex_log_handler(request: Request) -> JSONResponse:
    """Return the in-memory reindex job log (last 50 entries)."""
    return JSONResponse({"log": _reindex_log})


async def _api_logs_handler(request: Request) -> JSONResponse:
    """Return the last N lines of the rotating log file (default 200)."""
    try:
        n = int(request.query_params.get("lines", 200))
    except ValueError:
        n = 200
    log_path = DATA_DIR / "cortex.log"
    if not log_path.exists():
        return JSONResponse({"lines": []})
    text = log_path.read_text(errors="replace")
    lines = text.splitlines()
    return JSONResponse({"lines": lines[-n:]})
