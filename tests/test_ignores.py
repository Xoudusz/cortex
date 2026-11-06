"""repo_ignore_patterns: .cortexignore + .gdignore + .godot skip."""

import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "local"))

from pathlib import Path
from cortex.core.chunker import repo_ignore_patterns, _is_excluded, SKIP_DIRS
from cortex.indexer import _walk_code_files


def _tree(root: Path, files: list) -> None:
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n")


def test_cortexignore_and_gdignore():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _tree(root, ["scripts/player.gd", "addons/gut/gut.gd", "addons/dialogue/d.gd",
                     "vendor/lib.py", "src/vendor/inner.py", "web/app.min.js", "web/app.js",
                     "assets/raw/tool.py", ".godot/editor/x.gd"])
        (root / ".cortexignore").write_text("# third party\naddons/gut/\n/vendor\n*.min.js\n")
        (root / "assets" / "raw" / ".gdignore").write_text("")
        pats = repo_ignore_patterns(root)
        found = {p.relative_to(root).as_posix() for p in _walk_code_files(root, pats)}
        assert found == {"scripts/player.gd", "addons/dialogue/d.gd", "src/vendor/inner.py", "web/app.js"}, found


def test_unanchored_matches_any_depth():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".cortexignore").write_text("generated/\n")
        pats = repo_ignore_patterns(root)
        assert _is_excluded("a/b/generated/x.py", pats) and _is_excluded("generated/x.py", pats)
        assert not _is_excluded("a/generated_code.py", pats)


def test_godot_in_skip_dirs():
    assert ".godot" in SKIP_DIRS


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
