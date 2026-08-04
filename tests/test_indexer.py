"""Indexer edge-case + timing tests — tests _walk_code_files without embedding."""

import sys
import os
import tempfile
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "local"))

from pathlib import Path
from cortex.indexer import _walk_code_files
from cortex.core.chunker import CODE_EXTS, SKIP_DIRS

FIXTURES = Path(__file__).parent / "fixtures"


def test_walk_skips_node_modules():
    found = _walk_code_files(FIXTURES, [])
    assert not any("node_modules" in str(p) for p in found), \
        "node_modules/ must be pruned by SKIP_DIRS"


def test_walk_skips_bin():
    found = _walk_code_files(FIXTURES, [])
    assert not any(os.sep + "bin" + os.sep in str(p) or str(p).endswith(os.sep + "bin") for p in found), \
        "bin/ must be pruned by SKIP_DIRS"


def test_walk_skips_no_extension():
    found = _walk_code_files(FIXTURES, [])
    assert not any(p.suffix == "" for p in found), \
        "files with no extension must not appear (not in CODE_EXTS)"


def test_walk_respects_exclude_patterns():
    found_all = _walk_code_files(FIXTURES, [])
    found_excl = _walk_code_files(FIXTURES, ["generated/*"])
    all_names = {p.name for p in found_all}
    excl_names = {p.name for p in found_excl}
    assert "output.py" in all_names, "output.py should exist without exclusion"
    assert "output.py" not in excl_names, "output.py must be excluded by 'generated/*' pattern"


def test_walk_finds_fixture_src_files():
    found = _walk_code_files(FIXTURES, [])
    names = {p.name for p in found}
    assert "tiny.py" in names
    assert "huge.py" in names
    assert "syntax_error.js" in names
    assert "Component.razor" in names


def test_walk_only_code_exts():
    found = _walk_code_files(FIXTURES, [])
    for p in found:
        assert p.suffix in CODE_EXTS, f"{p.name} has unexpected extension {p.suffix}"


def test_walk_performance_large_tree():
    """`_walk_code_files` with SKIP_DIRS completes <5s on 500-file tree with blocked subtree."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        src = root / "src"
        src.mkdir()
        for i in range(300):
            (src / f"file_{i}.py").write_text(f"x = {i}")

        nm = root / "node_modules"
        nm.mkdir()
        for i in range(200):
            (nm / f"dep_{i}.js").write_text(f"module.exports = {i}")

        start = time.monotonic()
        found = _walk_code_files(root, [])
        elapsed = time.monotonic() - start

        assert len(found) == 300, f"expected 300 files, got {len(found)} (node_modules must be pruned)"
        assert elapsed < 5.0, f"walk took {elapsed:.2f}s — too slow (SKIP_DIRS pruning not working?)"
        assert not any("node_modules" in str(p) for p in found)


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
