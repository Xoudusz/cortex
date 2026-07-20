#!/usr/bin/env python3
"""FastMCP instance and tool registration for cortex."""

from mcp.server.fastmcp import FastMCP

from config import HOST, PORT
from tools_search import register_search
from tools_admin import register_admin

mcp = FastMCP("cortex", host=HOST, port=PORT)
register_search(mcp)
register_admin(mcp)
