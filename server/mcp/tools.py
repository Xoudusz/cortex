#!/usr/bin/env python3
"""MCP server instance and tool registration for cortex."""

from mcp.server.mcpserver import MCPServer

from config import ADMIN_PASSWORD
import oauth as _oauth
import state as _state
import users as _users
from tools_search import register_search
from tools_admin import register_admin
from tools_users import register_users

# Tools only the admin may call. Everything else works for members inside their granted workspaces.
ADMIN_TOOLS = frozenset({
    "clear_cache", "get_stats",
    "create_workspace", "delete_workspace", "set_workspace_wiki",
    "add_repo", "remove_repo",
    "invite_user", "list_users", "remove_user", "grant_workspace", "revoke_workspace",
})


def _request_user(context) -> str | None:
    """User behind this tool call: the Bearer token of the POST /messages request that carried it."""
    try:
        request = context.request_context.request
    except Exception:
        return None
    if request is None:
        return None
    return _oauth.token_user(_oauth.bearer_token(request.headers))


class CortexMCP(MCPServer):
    """MCPServer that binds the calling user before every tool call.

    SSE tool calls run in the GET /sse stream's task, not in the POST request that carried them,
    so the HTTP middleware's binding never reaches them — resolve the user here instead.
    """

    async def call_tool(self, name, arguments, context=None):
        if not ADMIN_PASSWORD:  # auth off: single-user mode, legacy global workspace
            return await super().call_tool(name, arguments, context)
        user = _request_user(context)
        if user is None:
            raise PermissionError("Not authenticated.")
        if name in ADMIN_TOOLS and not _users.is_admin(user):
            raise PermissionError(f"'{name}' is admin only.")
        tokens = _state.bind_request(user)
        try:
            return await super().call_tool(name, arguments, context)
        finally:
            _state.unbind_request(tokens)


mcp = CortexMCP("cortex")
register_search(mcp)
register_admin(mcp)
register_users(mcp)
