"""Incremental index e2e: changed files replace old points, deleted files vanish, roots are
recorded. Uses real embeddings (downloads fastembed models on first run) and a temp home."""

import os
import sys
import tempfile
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "local"))

from pathlib import Path

_home = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["USERPROFILE"] = _home

import cortex.config as config  # noqa: E402  (after HOME is set)
from cortex import db  # noqa: E402
from cortex.indexer import index_path  # noqa: E402
from cortex.core.formatters import format_code_results  # noqa: E402

BIG = "\n".join(f"def f{i}():\n    return {i}\n\n" for i in range(40))


def _points(collection: str) -> list:
    pts, _ = db.client().scroll(collection, limit=1000, with_payload=True)
    return [p.payload for p in pts]


def test_incremental_replace_and_delete():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "svc"
        (root / "src").mkdir(parents=True)
        (root / "src" / "a.py").write_text(BIG)
        (root / "src" / "gone.py").write_text("def gone():\n    return 1\n")
        (root / "README.md").write_text("# Title\n\nold text\n\n## Section\n\nmore\n")
        index_path(root)

        posix = root.resolve().as_posix()
        code = _points("code")
        assert code and all(p["root"] == posix and "\\" not in p["file"] for p in code)
        assert {p["file"] for p in code} == {"src/a.py", "src/gone.py"}
        meta = config.read_index_meta()["roots"][posix]
        assert meta["code"] == len(code) and meta["notes"] == 2 and meta["indexed_at"] <= time.time()

        # shrink a.py (old chunks must not survive), delete gone.py, edit README heading
        time.sleep(0.01)
        (root / "src" / "a.py").write_text("def only():\n    return 0\n")
        (root / "src" / "gone.py").unlink()
        (root / "README.md").write_text("# Title\n\nnew text\n")
        index_path(root)

        code = _points("code")
        assert [p["file"] for p in code] == ["src/a.py"], code
        assert "only" in code[0]["text"]
        notes = _points("notes")
        assert len(notes) == 1 and "new text" in notes[0]["text"], notes

        # result formatting: absolute POSIX path, no synthetic header
        class R:  # minimal qdrant point stand-in
            payload = code[0]
            score = 1.0
        out = format_code_results([(1.0, R, {})])
        assert f"**{posix}/src/a.py**" in out and "\n# svc" not in out, out


def test_two_roots_do_not_clobber_each_other():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("one", "two"):
            d = Path(tmp) / name
            d.mkdir()
            (d / "README.md").write_text(f"# Same\n\n{name}\n")
            index_path(d)
        texts = sorted(p["text"] for p in _points("notes") if p["root"].startswith(Path(tmp).resolve().as_posix()))
        assert texts == ["Same\n\none", "Same\n\ntwo"], texts


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
