#!/usr/bin/env python3
"""ASGI middleware for cortex-mcp: Bearer token auth and SSE path normalization."""

import logging

from starlette.responses import JSONResponse

from config import ADMIN_PASSWORD, BASE_URL
import oauth as _oauth
import state as _state
import users as _users

log = logging.getLogger("cortex")


bearer_token = _oauth.bearer_token


def _dashboard_ws(scope) -> str:
    """Workspace picked in the dashboard switcher (x-cortex-workspace); "default" if missing or unknown."""
    ws = ""
    for k, v in scope.get("headers", []):
        if k == b"x-cortex-workspace":
            ws = v.decode("latin-1").strip()
            break
    if ws == "default" or (ws and ws in _users.list_registered()):
        return ws
    if ws:
        log.debug("[dashboard] unknown workspace %r in x-cortex-workspace, using default", ws)
    return "default"


class _BearerTokenMiddleware:
    """Enforce Bearer token authentication on all protected routes and bind the caller.

    Routes in _UNPROTECTED and paths under /.well-known/ and /invite/ bypass auth.
    When ADMIN_PASSWORD is not set the middleware is a no-op (open access, single user).
    Returns 401 with WWW-Authenticate header on missing or invalid tokens.
    Members (non-admin users) may only use MCP (/sse) and /api/me — the dashboard API is admin-only.
    """

    _UNPROTECTED = frozenset({"/health", "/webhook", "/register", "/oauth/authorize", "/token", "/", "/favicon.svg"})
    _MEMBER_API = frozenset({"/api/me"})

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not ADMIN_PASSWORD:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self._UNPROTECTED or path.startswith(("/.well-known", "/invite/")):
            await self.app(scope, receive, send)
            return
        user = _oauth.token_user(bearer_token(scope.get("headers", [])))
        if user is None:
            log.warning("[auth] rejected %s — missing or invalid Bearer token", path)
            resource_meta = BASE_URL + "/.well-known/oauth-protected-resource"
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer resource_metadata="{resource_meta}"'},
            )
            await response(scope, receive, send)
            return
        if path.startswith("/api/") and path not in self._MEMBER_API and not _users.is_admin(user):
            await JSONResponse({"error": "admin only"}, status_code=403)(scope, receive, send)
            return
        # Admin dashboard API: bind the workspace chosen in the dashboard switcher (x-cortex-workspace header),
        # falling back to "default" when the header is missing or names an unknown workspace. Shared workspaces
        # also have explicit /api/workspaces/{name}/... routes. Members and non-/api paths keep ws=None.
        ws = _dashboard_ws(scope) if path.startswith("/api/") and _users.is_admin(user) else None
        tokens = _state.bind_request(user, ws)
        try:
            await self.app(scope, receive, send)
        finally:
            _state.unbind_request(tokens)


class _NormalizeSSEPath:
    """Rewrite /sse → /sse/sse to match FastMCP's internal SSE mount point."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/sse":
            scope = dict(scope)
            scope["path"] = "/sse/sse"
        await self.app(scope, receive, send)
