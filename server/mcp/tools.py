#!/usr/bin/env python3
"""MCP server instance and tool registration for cortex."""

from mcp.server.mcpserver import MCPServer

from tools_search import register_search
from tools_admin import register_admin

mcp = MCPServer("cortex")
register_search(mcp)
register_admin(mcp)
