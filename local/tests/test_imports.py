"""Smoke tests — validate local package imports and critical instantiations before PyPI publish."""

import sys


def test_mcp_import():
    from mcp.server.mcpserver import MCPServer
    assert MCPServer is not None


def test_mcp_instantiation():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("cortex-test")
    assert mcp is not None


def test_qdrant_client_import():
    from qdrant_client import QdrantClient
    assert QdrantClient is not None


def test_fastembed_import():
    from fastembed import TextEmbedding
    assert TextEmbedding is not None


def test_click_import():
    import click
    assert click is not None


def test_mcp_server_module():
    from cortex.mcp_server import mcp
    assert mcp is not None


def test_cli_module():
    from cortex.cli import cli
    assert cli is not None


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
