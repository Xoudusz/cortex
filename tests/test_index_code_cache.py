"""Incremental code-index path keeps the embed cache in step (no Qdrant/Ollama: fakes only)."""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "server", "indexer"),
                os.path.join(os.path.dirname(__file__), "..", "core")]

import index_code  # noqa: E402

REPO = "Xoudusz/fakerepo"
NAME = "fakerepo"


class FakeQdrant:
    def __init__(self, url=None):
        pass

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=index_code.COLLECTION)])

    def get_collection(self, name):
        return SimpleNamespace(points_count=5)

    def delete(self, *a, **k):
        pass

    def upsert(self, *a, **k):
        pass

    def set_payload(self, *a, **k):
        pass


def _fake_chunk_file(path, repo, base_dir=None, roslyn_data=None):
    rel = Path(path).relative_to(base_dir).as_posix()
    return [{"repo": repo, "file": rel, "start_line": 1, "text": "x", "chunk_type": "file"}]


def _fake_sparse(text):
    raise RuntimeError("no sparse model in test")  # dense-only path


def _run_main(argv, repos_dir, data_dir, repos_config):
    """Call index_code.main() with fakes; restore every patched attribute afterwards."""
    patches = [
        (index_code, "QdrantClient", FakeQdrant),
        (index_code, "_load_repos", lambda: [REPO]),
        (index_code, "clone_or_pull", lambda repo: repos_dir / NAME),
        (index_code, "chunk_file", _fake_chunk_file),
        (index_code, "embed", lambda text: [0.0] * index_code.VECTOR_SIZE),
        (index_code, "sparse_embed", _fake_sparse),
        (index_code, "REPOS_DIR", repos_dir),
        (index_code, "DATA_DIR", data_dir),
        (index_code.roslyn_analyzer, "is_available", lambda: False),
        (sys, "argv", ["index_code.py"] + argv),
    ]
    saved_env = os.environ.get("REPOS_CONFIG")
    os.environ["REPOS_CONFIG"] = str(repos_config)
    originals = [(obj, attr, getattr(obj, attr)) for obj, attr, _ in patches]
    try:
        for obj, attr, val in patches:
            setattr(obj, attr, val)
        index_code.main()
    finally:
        for obj, attr, orig in originals:
            setattr(obj, attr, orig)
        if saved_env is None:
            os.environ.pop("REPOS_CONFIG", None)
        else:
            os.environ["REPOS_CONFIG"] = saved_env


def test_incremental_remove_and_reembed_update_cache():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        repos_dir = root / "repos"
        repo_dir = repos_dir / NAME
        repo_dir.mkdir(parents=True)
        content = b"print(1)\n"
        (repo_dir / "a.py").write_bytes(content)
        repos_config = root / "repos.json"
        cache_file = root / "embed_cache.json"
        cache_file.write_text(json.dumps({"code": {
            f"{NAME}/gone.py": {"mtime": 1.0, "hash": "x"},
            f"{NAME}/keep.py": {"mtime": 2.0, "hash": "y"},
        }}))

        # run 1: re-embed a.py and remove gone.py (the path that used to raise UnboundLocalError)
        _run_main(["--files", "a.py", "--remove-files", "gone.py"], repos_dir, root, repos_config)
        code = json.loads(cache_file.read_text())["code"]
        assert f"{NAME}/gone.py" not in code
        assert code[f"{NAME}/keep.py"] == {"mtime": 2.0, "hash": "y"}
        assert code[f"{NAME}/a.py"] == {
            "mtime": (repo_dir / "a.py").stat().st_mtime,
            "hash": hashlib.sha1(content).hexdigest()[:16],
        }

        # run 2: remove-only run
        _run_main(["--remove-files", "keep.py"], repos_dir, root, repos_config)
        code = json.loads(cache_file.read_text())["code"]
        assert f"{NAME}/keep.py" not in code
        assert f"{NAME}/a.py" in code
        assert not any(n.endswith(".tmp") for n in os.listdir(root))  # atomic save left no temp file


if __name__ == "__main__":
    import traceback
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, t in tests:
        try:
            t()
            print(f"ok {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
