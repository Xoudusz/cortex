#!/usr/bin/env python3
"""Cortex MCP server — startup, routing, and middleware wiring."""

import logging
import logging.handlers
import threading

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from config import DATA_DIR, HOST, PORT, VERSION, warmup, ALLOWED_HOSTS
from state import _stats_saver
from reindex import _reindex_worker
from middleware import _BearerTokenMiddleware, _NormalizeSSEPath
from watcher import _start_watcher
from routes import (
    health, favicon, webhook,
    _ui_handler, _api_search_handler, _api_status_handler, _api_reindex_handler,
    _api_stats_handler, _api_graph_handler, _api_repos_handler, _api_repos_delete,
    _api_repos_meta_handler, _api_github_repos, _api_github_repo_check, _api_settings_handler, _api_webhook_log_handler,
    _api_reindex_log_handler, _api_logs_handler, _api_clear_cache_handler,
    _api_me_handler, _api_users_handler, _api_user_delete, _api_user_workspaces, _api_invites_handler,
    _api_workspaces_handler, _api_workspace_item, _api_workspace_repos, _api_workspace_reindex,
)
from tools import mcp
import oauth as _oauth

_BANNER = r"""
   ██████╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗
  ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝
  ██║     ██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝
  ██║     ██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗
  ╚██████╗╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗
   ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
"""


if __name__ == "__main__":
    print(_BANNER, flush=True)
    print(f"  RAG stack  ·  v{VERSION}  ·  MCP SSE server\n", flush=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                DATA_DIR / "cortex.log", maxBytes=5 * 1024 * 1024, backupCount=3
            ),
        ],
        force=True,
    )
    threading.Thread(target=warmup, daemon=True).start()
    threading.Thread(target=_start_watcher, daemon=True).start()
    threading.Thread(target=_stats_saver, daemon=True).start()
    threading.Thread(target=_reindex_worker, daemon=True).start()
    _transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(ALLOWED_HOSTS),
        allowed_hosts=ALLOWED_HOSTS,
    )
    sse_app = mcp.sse_app(transport_security=_transport_security)
    starlette_app = Starlette(routes=[
        Route("/health", health, methods=["GET"]),
        Route("/favicon.svg", favicon, methods=["GET"]),
        Route("/webhook", webhook, methods=["POST"]),
        Route("/", _ui_handler, methods=["GET"]),
        Route("/api/search", _api_search_handler, methods=["POST"]),
        Route("/api/status", _api_status_handler, methods=["GET"]),
        Route("/api/reindex", _api_reindex_handler, methods=["POST"]),
Route("/api/clear-cache", _api_clear_cache_handler, methods=["POST"]),
        Route("/api/stats", _api_stats_handler, methods=["GET"]),
        Route("/api/repos", _api_repos_handler, methods=["GET", "POST"]),
        Route("/api/repos/{repo:path}", _api_repos_delete, methods=["DELETE"]),
        Route("/api/repos-meta", _api_repos_meta_handler, methods=["GET"]),
        Route("/api/github/repos", _api_github_repos, methods=["GET"]),
        Route("/api/github/repo-check", _api_github_repo_check, methods=["GET"]),
        Route("/api/settings", _api_settings_handler, methods=["GET", "PUT", "DELETE"]),
        Route("/api/webhook-log", _api_webhook_log_handler, methods=["GET"]),
        Route("/api/reindex-log", _api_reindex_log_handler, methods=["GET"]),
        Route("/api/logs", _api_logs_handler, methods=["GET"]),
        Route("/api/graph/{repo:path}", _api_graph_handler, methods=["GET"]),
        Route("/api/me", _api_me_handler, methods=["GET"]),
        Route("/api/users", _api_users_handler, methods=["GET"]),
        Route("/api/users/{name}", _api_user_delete, methods=["DELETE"]),
        Route("/api/users/{name}/workspaces", _api_user_workspaces, methods=["POST", "DELETE"]),
        Route("/api/invites", _api_invites_handler, methods=["POST"]),
        Route("/api/workspaces", _api_workspaces_handler, methods=["GET", "POST"]),
        Route("/api/workspaces/{name}", _api_workspace_item, methods=["PUT", "DELETE"]),
        Route("/api/workspaces/{name}/repos", _api_workspace_repos, methods=["POST"]),
        Route("/api/workspaces/{name}/repos/{repo:path}", _api_workspace_repos, methods=["DELETE"]),
        Route("/api/workspaces/{name}/reindex", _api_workspace_reindex, methods=["POST"]),
        Route("/invite/{token}", _oauth.invite_get, methods=["GET"]),
        Route("/invite/{token}", _oauth.invite_post, methods=["POST"]),
        Route("/.well-known/oauth-authorization-server", _oauth.well_known_as),
        Route("/.well-known/oauth-protected-resource", _oauth.well_known_resource),
        Route("/register", _oauth.register, methods=["POST"]),
        Route("/oauth/authorize", _oauth.authorize_get, methods=["GET"]),
        Route("/oauth/authorize", _oauth.authorize_post, methods=["POST"]),
        Route("/token", _oauth.token_endpoint, methods=["POST"]),
        Mount("/sse", app=sse_app),
    ])
    app = _NormalizeSSEPath(_BearerTokenMiddleware(starlette_app))
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
