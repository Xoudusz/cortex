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


def test_config_data_dir():
    from cortex.config import data_dir, WORKSPACES_DIR
    d = data_dir()
    assert str(WORKSPACES_DIR) in str(d)


def test_walk_code_files_skips_dirs():
    import os, tempfile
    from pathlib import Path
    from cortex.indexer import _walk_code_files
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "node_modules").mkdir()
        (root / "node_modules" / "lib.js").write_text("x")
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("x")
        found = _walk_code_files(root, [])
        paths = [str(p) for p in found]
        assert any("main.py" in p for p in paths)
        assert not any("node_modules" in p for p in paths)


def test_is_excluded_patterns():
    from cortex.core.chunker import _is_excluded
    assert _is_excluded("tmp/foo.log", ["tmp/*"])
    assert not _is_excluded("src/main.py", ["tmp/*"])
    assert _is_excluded("dist/bundle.js", ["dist/*"])


def test_fmt_stats_returns_string():
    from cortex.core.formatters import fmt_stats
    result = fmt_stats("2.3.8", {}, current=True)
    assert isinstance(result, str)
    assert len(result) > 0


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
