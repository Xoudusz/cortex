"""Chunker edge-case tests — no network, no embedding, no Qdrant."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "local"))

from pathlib import Path
from cortex.core.chunker import chunk_file, SKIP_DIRS, CODE_EXTS, MAX_CHUNK_LINES

FIXTURES = Path(__file__).parent / "fixtures"


def test_empty_file_returns_no_chunks():
    chunks = chunk_file(FIXTURES / "src" / "empty.py", "test")
    assert chunks == []


def test_tiny_file_single_chunk():
    chunks = chunk_file(FIXTURES / "src" / "tiny.py", "test")
    assert len(chunks) >= 1
    # ≤80 lines means tree-sitter produces per-function chunks OR single sliding-window chunk
    # key: does not error, produces at least one chunk
    assert all("text" in c and "file" in c for c in chunks)


def test_huge_file_multiple_chunks():
    chunks = chunk_file(FIXTURES / "src" / "huge.py", "test")
    assert len(chunks) > 1, f"expected >1 chunks for 120-line file, got {len(chunks)}"


def test_syntax_error_no_crash():
    chunks = chunk_file(FIXTURES / "src" / "syntax_error.js", "test")
    assert isinstance(chunks, list)  # must not raise — fallback to sliding window


def test_only_comments_no_crash():
    chunks = chunk_file(FIXTURES / "src" / "only_comments.py", "test")
    assert isinstance(chunks, list)


def test_razor_produces_razor_chunk():
    chunks = chunk_file(FIXTURES / "src" / "Component.razor", "test")
    assert len(chunks) >= 1
    languages = {c["language"] for c in chunks}
    assert "razor" in languages, f"expected 'razor' language, got {languages}"


def test_razor_extracts_csharp_code_block():
    chunks = chunk_file(FIXTURES / "src" / "Component.razor", "test")
    languages = {c["language"] for c in chunks}
    assert "csharp" in languages, f"expected 'csharp' @code block chunk, got {languages}"


def test_chunk_fields_complete():
    chunks = chunk_file(FIXTURES / "src" / "tiny.py", "test")
    for c in chunks:
        for field in ("repo", "file", "language", "start_line", "end_line", "text"):
            assert field in c, f"missing field '{field}' in chunk"


def test_chunk_text_contains_path_tokens():
    chunks = chunk_file(FIXTURES / "src" / "tiny.py", "myrepo")
    assert chunks
    assert "myrepo" in chunks[0]["text"]


def test_skip_dirs_covers_known_dirs():
    for d in ("node_modules", "bin", "obj", ".git", "dist", "build", "__pycache__"):
        assert d in SKIP_DIRS, f"'{d}' missing from SKIP_DIRS"


def test_code_exts_covers_common_types():
    for ext in (".py", ".ts", ".js", ".cs", ".razor", ".go", ".rs"):
        assert ext in CODE_EXTS, f"'{ext}' missing from CODE_EXTS"


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
