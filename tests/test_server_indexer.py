"""Server indexer helpers — no network, no Qdrant."""

import os
import sys

sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "server", "indexer"),
                os.path.join(os.path.dirname(__file__), "..", "core")]
os.environ["GITHUB_TOKEN"] = "ghp_secret123"

import index_code  # noqa: E402

index_code.TOKEN = "ghp_secret123"


def test_git_error_masks_token_and_hints_auth():
    err = ("Cloning into '/tmp/repos/x'...\n"
           "remote: Invalid username or token.\n"
           "fatal: Authentication failed for 'https://Xoudusz:ghp_secret123@github.com/a/b.git/'\n")
    msg = index_code.git_error(err)
    assert "ghp_secret123" not in msg and "***" in msg
    assert "Authentication failed" in msg and "hint: GitHub token" in msg


def test_git_error_repo_not_found_hint():
    msg = index_code.git_error("remote: Repository not found.\nfatal: repository 'https://x' not found\n")
    assert "classic PAT" in msg


def test_git_error_empty():
    assert index_code.git_error("") == "git printed no error"

import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import index  # noqa: E402


def _fences_balanced(text):
    st = None
    for ln in text.split("\n"):
        m = index._FENCE.match(ln)
        if m:
            if st is None:
                st = m.group(1)
            elif m.group(1) == st and not m.group(2).strip():
                st = None
    return st is None


def test_split_short_body_unchanged():
    assert index.split_body("hello\n\nworld") == ["hello\n\nworld"]


def test_split_long_body_parts_under_limit_and_complete():
    paras = [f"para {i} " + "word " * 80 for i in range(40)]
    body = "\n\n".join(paras)
    parts = index.split_body(body)
    assert len(parts) > 1
    assert all(len(p) <= index.MAX_CHUNK_CHARS for p in parts)
    assert "\n\n".join(parts).split() == body.split()


def test_split_overlong_paragraph_hard_split():
    body = "x" * 7000
    parts = index.split_body(body)
    assert all(len(p) <= index.MAX_CHUNK_CHARS for p in parts)
    assert "".join(parts) == body


def test_split_inside_fence_closes_and_reopens():
    code = "\n\n".join(f"print({i})  # " + "y" * 200 for i in range(30))
    body = "intro text\n\n```python\n" + code + "\n```\n\nafter"
    parts = index.split_body(body)
    assert len(parts) > 1
    assert all(len(p) <= index.MAX_CHUNK_CHARS for p in parts)
    assert all(_fences_balanced(p) for p in parts), "every part must have balanced fences"
    assert all(p.split("\n")[0] == "```python" or not p.startswith("```python") for p in parts[1:])
    assert "```python" in parts[1]  # reopened in the continuation part


def test_chunk_markdown_unique_ids_for_split_section():
    with tempfile.TemporaryDirectory() as d:
        index.NOTES_DIR = Path(d)
        f = Path(d) / "big.md"
        f.write_text("# Big\n\n" + "\n\n".join("text " * 150 + str(i) for i in range(10)), encoding="utf-8")
        chunks = index.chunk_markdown(f)
        assert len(chunks) > 1
        ids = [index.chunk_id(c["file"], c["heading"]) for c in chunks]
        assert len(set(ids)) == len(ids), "split parts must not collide in chunk_id"
        assert all(c["text"].startswith("Big\n\n") for c in chunks)


def test_chunk_markdown_small_note_keeps_heading_ids():
    with tempfile.TemporaryDirectory() as d:
        index.NOTES_DIR = Path(d)
        f = Path(d) / "small.md"
        f.write_text("# A\n\nshort\n\n## B\n\nshort too\n", encoding="utf-8")
        assert [c["heading"] for c in index.chunk_markdown(f)] == ["A", "B"]



if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  ok  {t.__name__}")
        except Exception:
            failed += 1; print(f"  FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
