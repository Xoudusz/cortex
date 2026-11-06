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

from config import DATA_DIR, get_github_token, read_settings, write_settings, OLLAMA_URL, QDRANT_URL, STATS_FILE, VERSION, WEBHOOK_SECRET, embed, sparse_embed
from state import _reindex_log, _stats, _webhook_log
from repos import _load_repos, _load_repos_meta, _save_repos
from reindex import _enqueue, get_status, get_queue_snapshot, clear_cache as _clear_cache
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
    status = _enqueue(False, True, repo, files=changed if (changed or removed) else None, removed=removed, _log_entry=log_entry)
    log_entry["status"] = status
    log.info("[webhook] push on %s -> %d changed, %d removed -> %s", repo or "unknown", len(changed), len(removed), status)
    return JSONResponse({"status": "ok", "repo": repo, "files_changed": len(changed)})


async def _ui_handler(request: Request):
    """Serve the web dashboard HTML."""
    return await ui(request)


async def _api_search_handler(request: Request):
    """Proxy semantic search requests to the Qdrant-backed search handler."""
    return await api_search(request, QDRANT_URL, embed, sparse_embed)


async def _api_status_handler(request: Request):
    """Return the current reindex job state and queue snapshot."""
    return await api_status(request, get_status(), get_queue_snapshot())


async def _api_reindex_handler(request: Request):
    """Enqueue a reindex job from a JSON body with notes/code/repo flags."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    force = body.get("force", False)
    _enqueue(body.get("notes", True), body.get("code", True), body.get("repo", ""), files=None, force=force)
    return JSONResponse({"status": "queued", "force": force})


async def _api_clear_cache_handler(request: Request):
    """Clear embed cache for current or all workspaces."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    all_workspaces = body.get("all_workspaces", False)
    n = _clear_cache(all_workspaces=all_workspaces)
    scope = "all workspaces" if all_workspaces else "current workspace"
    return JSONResponse({"deleted": n, "scope": scope})


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


def _gh_headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


async def _api_github_repos(request: Request) -> JSONResponse:
    """All non-archived repos the token can see: owned, collaborator and organisation (paginated)."""
    token, _ = get_github_token()
    if not token:
        return JSONResponse({"error": "No GitHub token configured (Admin > Settings)"}, status_code=503)
    repos: list = []
    url = "https://api.github.com/user/repos"
    params = {"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(10):  # up to 1000 repos
                resp = await client.get(url, headers=_gh_headers(token), params=params)
                resp.raise_for_status()
                repos += [r["full_name"] for r in resp.json() if not r.get("archived")]
                nxt = resp.links.get("next", {}).get("url")
                if not nxt:
                    break
                url, params = nxt, None
        return JSONResponse({"repos": repos})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _token_info(token: str, source: str) -> dict:
    info = {"set": bool(token), "source": source}
    if not token:
        return info
    info["hint"] = token[:4] + "..." + token[-4:]
    info["type"] = "fine-grained" if token.startswith("github_pat_") else "classic" if token.startswith("ghp_") else "other"
    return info


async def _validate_token(token: str) -> dict:
    """Ask GitHub who the token belongs to; classic tokens also report their scopes."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.github.com/user", headers=_gh_headers(token))
    if resp.status_code == 401:
        raise ValueError("GitHub rejected the token (401)")
    resp.raise_for_status()
    scopes = [x.strip() for x in resp.headers.get("x-oauth-scopes", "").split(",") if x.strip()]
    return {"login": resp.json().get("login", ""), "scopes": scopes}


async def _api_settings_handler(request: Request) -> JSONResponse:
    """GET: token status (never the token). PUT {github_token}: validate + store. DELETE: clear."""
    if request.method == "PUT":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        token = str(body.get("github_token", "")).strip()
        if not token:
            return JSONResponse({"error": "github_token is empty"}, status_code=400)
        try:
            who = await _validate_token(token)
        except Exception as e:
            return JSONResponse({"error": f"token check failed: {e}"}, status_code=400)
        settings = read_settings()
        settings["github_token"] = token
        write_settings(settings)
        log.info("[settings] GitHub token updated (user %s)", who["login"])
        return JSONResponse({**_token_info(token, "settings"), **who})
    if request.method == "DELETE":
        settings = read_settings()
        settings.pop("github_token", None)
        write_settings(settings)
        log.info("[settings] GitHub token cleared from settings")
    token, source = get_github_token()
    info = _token_info(token, source)
    if token:
        try:
            info.update(await _validate_token(token))
        except Exception as e:
            info["error"] = str(e)
    return JSONResponse(info)


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
