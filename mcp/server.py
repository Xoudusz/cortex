#!/usr/bin/env python3
"""Cortex MCP server — HTTP routes, middleware, watcher, and startup."""

import hashlib
import hmac
import json
import logging
import logging.handlers
import os
import threading
from datetime import datetime, timezone

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import (
    ADMIN_PASSWORD, BASE_URL, DATA_DIR, GITHUB_TOKEN, NOTES_PATH,
    OLLAMA_URL, QDRANT_URL, STATS_FILE, VERSION,
    WATCH_DEBOUNCE, WEBHOOK_SECRET, HOST, PORT,
    _load_repos, _load_repos_meta, _save_repos,
    _update_indexed_at, _webhook_log, _stats_saver, embed, warmup,
)
from reindex import _enqueue, _job_lock, _job_queue, _reindex_state, _reindex_worker
from tools import mcp
from web_ui import ui, api_search, api_status, api_stats, LOGO_SVG
import oauth as _oauth

import httpx

log = logging.getLogger("cortex")


class _NotesHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer = None

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
        log.info("[watcher] debounce elapsed — queuing notes reindex")
        _enqueue(notes=True, code=False)


class _BearerTokenMiddleware:
    _UNPROTECTED = frozenset({"/health", "/webhook", "/register", "/authorize", "/token", "/", "/favicon.svg"})

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and ADMIN_PASSWORD:
            path = scope.get("path", "")
            unprotected = path in self._UNPROTECTED or path.startswith("/.well-known")
            if not unprotected:
                headers = {k: v for k, v in scope.get("headers", [])}
                auth = headers.get(b"authorization", b"").decode()
                token = auth[7:] if auth.startswith("Bearer ") else ""
                if not _oauth.verify_token(token):
                    log.warning("[auth] rejected %s — missing or invalid Bearer token", path)
                    resource_meta = BASE_URL + "/.well-known/oauth-protected-resource"
                    response = JSONResponse(
                        {"error": "unauthorized"},
                        status_code=401,
                        headers={"WWW-Authenticate": f'Bearer resource_metadata="{resource_meta}"'},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class _NormalizeSSEPath:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http' and scope.get('path') == '/sse':
            scope = dict(scope)
            scope['path'] = '/sse/sse'
        await self.app(scope, receive, send)


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def favicon(request: Request) -> Response:
    return Response(LOGO_SVG, media_type="image/svg+xml")


async def webhook(request: Request) -> JSONResponse:
    body = await request.body()
    if WEBHOOK_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            log.warning("[webhook] invalid signature — rejected")
            return JSONResponse({"error": "invalid signature"}, status_code=401)
    event = request.headers.get("X-GitHub-Event", "")
    if event != "push":
        return JSONResponse({"status": "ignored", "event": event})
    try:
        payload = json.loads(body)
        repo = payload.get("repository", {}).get("name", "")
        changed, removed = [], []
        for commit in payload.get("commits", []):
            changed += commit.get("added", []) + commit.get("modified", [])
            removed += commit.get("removed", [])
        removed = list(set(removed))
        changed = list(set(changed) - set(removed))
    except Exception:
        repo, changed, removed = "", [], []
    ts = datetime.now(timezone.utc).isoformat()
    status = _enqueue(False, True, repo, files=changed or None, removed=removed)
    _webhook_log.insert(0, {"repo": repo or "unknown", "ts": ts, "status": status, "files": len(changed)})
    _webhook_log[:] = _webhook_log[:50]
    log.info("[webhook] push on %s -> %d changed, %d removed -> %s", repo or "unknown", len(changed), len(removed), status)
    return JSONResponse({"status": "ok", "repo": repo, "files_changed": len(changed)})


async def _ui_handler(request: Request):
    return await ui(request)

async def _api_search_handler(request: Request):
    return await api_search(request, QDRANT_URL, embed)

async def _api_status_handler(request: Request):
    with _job_lock:
        queue_snapshot = [{"notes": j["notes"], "code": j["code"], "repo": j.get("repo", "")} for j in _job_queue]
    return await api_status(request, _reindex_state, queue_snapshot)

async def _api_reindex_handler(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    _enqueue(body.get("notes", True), body.get("code", True), body.get("repo", ""), files=None)
    return JSONResponse({"status": "queued"})

async def _api_stats_handler(request: Request):
    from config import _stats
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
    repo = request.path_params.get("repo", "")
    repos = [r for r in _load_repos() if r != repo]
    _save_repos(repos)
    log.info("[repos] removed %s", repo)
    return JSONResponse({"repos": repos})

async def _api_repos_meta_handler(request: Request) -> JSONResponse:
    return JSONResponse(_load_repos_meta())

async def _api_github_repos(request: Request) -> JSONResponse:
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
    return JSONResponse({"log": _webhook_log})


async def _api_logs_handler(request: Request) -> JSONResponse:
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


def _start_watcher():
    if not os.path.isdir(NOTES_PATH):
        log.warning("[watcher] notes path %s not found, skipping", NOTES_PATH)
        return
    observer = Observer()
    observer.schedule(_NotesHandler(), NOTES_PATH, recursive=True)
    observer.start()
    log.info("[watcher] watching %s for .md changes (debounce %ds)", NOTES_PATH, WATCH_DEBOUNCE)




if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                DATA_DIR / "cortex.log", maxBytes=5 * 1024 * 1024, backupCount=3
            ),
        ],
    )
    threading.Thread(target=warmup, daemon=True).start()
    threading.Thread(target=_start_watcher, daemon=True).start()
    threading.Thread(target=_stats_saver, daemon=True).start()
    threading.Thread(target=_reindex_worker, daemon=True).start()
    sse_app = mcp.sse_app()
    starlette_app = Starlette(routes=[
        Route("/health", health, methods=["GET"]),
        Route("/favicon.svg", favicon, methods=["GET"]),
        Route("/webhook", webhook, methods=["POST"]),
        Route("/", _ui_handler, methods=["GET"]),
        Route("/api/search", _api_search_handler, methods=["POST"]),
        Route("/api/status", _api_status_handler, methods=["GET"]),
        Route("/api/reindex", _api_reindex_handler, methods=["POST"]),
        Route("/api/stats", _api_stats_handler, methods=["GET"]),
        Route("/api/repos", _api_repos_handler, methods=["GET", "POST"]),
        Route("/api/repos/{repo:path}", _api_repos_delete, methods=["DELETE"]),
        Route("/api/repos-meta", _api_repos_meta_handler, methods=["GET"]),
        Route("/api/github/repos", _api_github_repos, methods=["GET"]),
        Route("/api/webhook-log", _api_webhook_log_handler, methods=["GET"]),
        Route("/api/logs", _api_logs_handler, methods=["GET"]),
        Route("/api/graph/{repo:path}", _api_graph_handler, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server", _oauth.well_known_as),
        Route("/.well-known/oauth-protected-resource", _oauth.well_known_resource),
        Route("/register", _oauth.register, methods=["POST"]),
        Route("/authorize", _oauth.authorize_get, methods=["GET"]),
        Route("/authorize", _oauth.authorize_post, methods=["POST"]),
        Route("/token", _oauth.token_endpoint, methods=["POST"]),
        Mount("/sse", app=sse_app),
    ])
    app = _NormalizeSSEPath(_BearerTokenMiddleware(starlette_app))
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
