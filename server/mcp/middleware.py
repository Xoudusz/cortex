#!/usr/bin/env python3
"""ASGI middleware for cortex-mcp: Bearer token auth and SSE path normalization."""

import logging

from starlette.responses import JSONResponse

from config import ADMIN_PASSWORD, BASE_URL
import oauth as _oauth

log = logging.getLogger("cortex")


class _BearerTokenMiddleware:
    """Enforce Bearer token authentication on all protected routes.

    Routes in _UNPROTECTED and paths under /.well-known/ bypass auth.
    When ADMIN_PASSWORD is not set the middleware is a no-op (open access).
    Returns 401 with WWW-Authenticate header on missing or invalid tokens.
    """

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
    """Rewrite /sse → /sse/sse to match FastMCP's internal SSE mount point."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/sse":
            scope = dict(scope)
            scope["path"] = "/sse/sse"
        await self.app(scope, receive, send)
