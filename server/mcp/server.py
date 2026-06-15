#!/usr/bin/env python3
"""Cortex MCP server — startup, routing, and middleware wiring."""

import logging
import logging.handlers
import threading

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from config import DATA_DIR, HOST, PORT, warmup
from state import _stats_saver
from reindex import _reindex_worker
from middleware import _BearerTokenMiddleware, _NormalizeSSEPath
from watcher import _start_watcher
from routes import (
    health, favicon, webhook,
    _ui_handler, _api_search_handler, _api_status_handler, _api_reindex_handler,
    _api_stats_handler, _api_graph_handler, _api_repos_handler, _api_repos_delete,
    _api_repos_meta_handler, _api_github_repos, _api_webhook_log_handler,
    _api_reindex_log_handler, _api_logs_handler,
)
from tools import mcp
import oauth as _oauth


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
        force=True,
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
        Route("/api/reindex-log", _api_reindex_log_handler, methods=["GET"]),
        Route("/api/logs", _api_logs_handler, methods=["GET"]),
        Route("/api/graph/{repo:path}", _api_graph_handler, methods=["GET"]),
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
