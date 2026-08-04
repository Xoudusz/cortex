"""Smoke tests — validate server imports and critical instantiations before Docker build.

Run via CI: PYTHONPATH=server/mcp:core python server/mcp/tests/test_imports.py
Run in Docker: python /app/tests/test_imports.py  (PYTHONPATH not needed — all files in /app)
"""

import os
import sys

# Support both CI (PYTHONPATH set externally) and direct runs from this dir
_here = os.path.dirname(os.path.abspath(__file__))
_server_mcp = os.path.join(_here, "..")
_core = os.path.join(_here, "..", "..", "..", "core")
for _p in (_server_mcp, _core):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stub env vars so config.py imports without network calls
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
