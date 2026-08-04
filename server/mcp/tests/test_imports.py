"""Smoke tests — validate server imports and critical instantiations before Docker build."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars so config.py doesn't blow up
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("BASE_URL", "http://localhost:8765")


def test_mcp_import():
    from mcp.server.mcpserver import MCPServer
    assert MCPServer is not None


def test_mcp_instantiation():
    from mcp.server.mcpserver import MCPServer
    mcp = MCPServer("cortex-test")
    assert mcp is not None


def test_transport_security_import():
    from mcp.server.transport_security import TransportSecuritySettings
    s = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["example.com"],
    )
    assert s.allowed_hosts == ["example.com"]


def test_qdrant_client_import():
    from qdrant_client import QdrantClient
    assert QdrantClient is not None


def test_starlette_import():
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    assert Starlette is not None


def test_config_import():
    import config
    assert hasattr(config, "HOST")
    assert hasattr(config, "PORT")
    assert hasattr(config, "ALLOWED_HOSTS")


def test_tools_import():
    from tools import mcp
    assert mcp is not None


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
