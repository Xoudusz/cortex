"""Regression tests for issue #4 / Windows local mode — no network, no embedding."""

import json
import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "local"))

from pathlib import Path, PureWindowsPath

import cortex.config as config
from cortex.core.chunker import chunk_file
from cortex.core.code_graph import build_code_graph

FIXTURES = Path(__file__).parent / "fixtures"


class _TempHome:
    """Point cortex.config at a throwaway ~/.cortex."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name) / ".cortex"
        self._saved = {k: getattr(config, k) for k in
                       ("CORTEX_DIR", "WORKSPACES_DIR", "CONFIG_FILE", "ACTIVE_WORKSPACE_FILE")}
        config.CORTEX_DIR = root
        config.WORKSPACES_DIR = root / "workspaces"
        config.CONFIG_FILE = root / "config.toml"
        config.ACTIVE_WORKSPACE_FILE = root / "active_workspace"
        config._config_cache = None
        return root

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            setattr(config, k, v)
        config._config_cache = None
        self._tmp.cleanup()


def test_chunk_paths_are_posix():
    chunks = chunk_file(FIXTURES / "src" / "huge.py", "repo", base_dir=FIXTURES)
    assert chunks and all("\\" not in c["file"] for c in chunks)
    assert chunks[0]["file"] == "src/huge.py"


def test_toml_value_escapes_windows_path():
    import tomllib
    raw = str(PureWindowsPath(r"C:\Users\me\work"))
    doc = f"[index]\nlast_path = {config._toml_value(raw)}\n"
    assert tomllib.loads(doc)["index"]["last_path"] == raw


def test_save_last_indexed_path_roundtrip():
    with _TempHome():
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            config.save_last_indexed_path(a)
            config.save_last_indexed_path(b)
            cfg = config.get_config()
            assert cfg["index"]["last_path"] == Path(b).resolve().as_posix()
            assert cfg["watch"]["enabled"] is True


def test_save_last_indexed_path_heals_corrupt_config():
    with _TempHome() as root:
        root.mkdir(parents=True)
        config.CONFIG_FILE.write_text('[index]\nlast_path = "C:\\Users\\me"\n')  # 2.4.5 output: invalid TOML
        with tempfile.TemporaryDirectory() as a:
            config.save_last_indexed_path(a)
            assert config.get_config()["index"]["last_path"] == Path(a).resolve().as_posix()


def test_schema_mismatch_wipes_old_index():
    with _TempHome():
        ws = config.get_workspace_dir()
        (ws / "qdrant").mkdir(parents=True)
        (ws / "embed_cache.json").write_text("{}")
        (ws / "graph_repo.json").write_text("{}")
        (ws / "stats.json").write_text("{}")
        assert config.ensure_index_schema() is True
        assert not (ws / "qdrant").exists()
        assert not (ws / "embed_cache.json").exists()
        assert not (ws / "graph_repo.json").exists()
        assert (ws / "stats.json").exists()  # stats survive
        assert json.loads((ws / "index_meta.json").read_text())["schema"] == config.INDEX_SCHEMA
        (ws / "qdrant").mkdir()
        assert config.ensure_index_schema() is False
        assert (ws / "qdrant").exists()


def test_kotlin_call_edges():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = root / "src/main/kotlin/org/example"
        (base / "service").mkdir(parents=True)
        (base / "util").mkdir(parents=True)
        (base / "service/FooService.kt").write_text(
            "package org.example.service\n\n"
            "import org.example.util.Formatter\n"
            "import org.example.util.parseId as pid\n\n"
            "class FooService(private val other: Unused?) {\n"  # type ref only: no call edge
            "    private val repo = FooRepository()\n"
            "    fun run() = Formatter.format(pid(\"1\"))\n"
            "}\n")
        (base / "service/FooRepository.kt").write_text(
            "package org.example.service\n\nclass FooRepository\n")
        (base / "service/Unused.kt").write_text(
            "package org.example.service\n\nclass Unused\n")
        (base / "util/Formatter.kt").write_text(
            "package org.example.util\n\nobject Formatter { fun format(s: String) = s }\n")
        (base / "util/Ids.kt").write_text(
            "package org.example.util\n\nfun parseId(s: String) = s\n")
        files = {p.relative_to(root).as_posix() for p in root.rglob("*.kt")}
        G = build_code_graph(root, files)
        src = "src/main/kotlin/org/example/service/FooService.kt"
        calls = {v for _, v, d in G.out_edges(src, data=True) if d["type"] == "call"}
        assert calls == {
            "src/main/kotlin/org/example/util/Formatter.kt",
            "src/main/kotlin/org/example/util/Ids.kt",
            "src/main/kotlin/org/example/service/FooRepository.kt",
        }, calls


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
