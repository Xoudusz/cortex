"""Token-savings accounting (core/savings.py), stats formatting, typed statuses, TUI renderable."""

import io
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "core"))
sys.path.insert(0, os.path.join(_HERE, "..", "local"))

import savings  # noqa: E402
import formatters  # noqa: E402

KB4 = 4000  # 1000 tokens
CHUNK = "x" * 400  # 100 tokens


def _store(ttl=1800):
    return savings.SessionStore(ttl)


def test_observed_math():
    st = {}
    savings.record_code(st, _store(), ("u", "w"), [("r", "a.py", CHUNK, {"bytes": KB4})], [])
    assert st["tokens_observed_code"] == 900
    assert st["savings_hits_measured"] == 1
    assert st["savings_by_repo"]["r"]["observed"] == 900
    assert st["savings_by_repo"]["r"]["hits"] == 1
    assert "savings_by_user" in st and st["savings_by_user"] == {}


def test_observed_never_negative():
    st = {}
    savings.record_code(st, _store(), "k", [("r", "a.py", "x" * 8000, {"bytes": 40})], [])
    assert st["tokens_observed_code"] == 0


def test_dedup_same_session():
    st, s = {}, _store()
    h = [("r", "a.py", CHUNK, {"bytes": KB4})]
    savings.record_code(st, s, "k", h, [])
    savings.record_code(st, s, "k", h, [])
    assert st["tokens_observed_code"] == 900


def test_different_session_recounts():
    st, s = {}, _store()
    h = [("r", "a.py", CHUNK, {"bytes": KB4})]
    savings.record_code(st, s, "k1", h, [])
    savings.record_code(st, s, "k2", h, [])
    assert st["tokens_observed_code"] == 1800


def test_ttl_boundaries():
    h = [("r", "a.py", CHUNK, {"bytes": KB4})]
    st, s = {}, _store(1800)
    savings.record_code(st, s, "k", h, [], now=0)
    savings.record_code(st, s, "k", h, [], now=1799)
    assert st["tokens_observed_code"] == 900
    st, s = {}, _store(1800)
    savings.record_code(st, s, "k", h, [], now=0)
    savings.record_code(st, s, "k", h, [], now=1801)
    assert st["tokens_observed_code"] == 1800


def test_ttl_none_never_resets():
    h = [("r", "a.py", CHUNK, {"bytes": KB4})]
    st, s = {}, _store(None)
    savings.record_code(st, s, "k", h, [], now=0)
    savings.record_code(st, s, "k", h, [], now=10**9)
    assert st["tokens_observed_code"] == 900


def test_unmeasured():
    st, s = {}, _store()
    h = [("r", "a.py", CHUNK, {})]
    savings.record_code(st, s, "k", h, [])
    savings.record_code(st, s, "k", h, [])
    assert st["savings_hits_unmeasured"] == 1
    assert st["tokens_observed_code"] == 0


def test_modeled_excludes_returned_and_counted():
    st, s = {}, _store()
    hits = [("r", "a.py", CHUNK, {"bytes": KB4})]
    cands = [("r", "a.py", {"bytes": KB4}), ("r", "b.py", {"bytes": KB4}),
             ("r", "b.py", {"bytes": KB4}), ("r", "c.py", {})]
    savings.record_code(st, s, "k", hits, cands)
    assert st["tokens_modeled_code"] == 500
    savings.record_code(st, s, "k", [], cands)
    assert st["tokens_modeled_code"] == 500
    assert st["savings_by_repo"]["r"]["modeled"] == 500


def test_per_user_buckets():
    st = {}
    savings.record_code(st, _store(), "k", [("r", "a.py", CHUNK, {"bytes": KB4})], [], user="alice")
    assert st["savings_by_user"]["alice"]["observed"] == 900
    st2 = {}
    savings.record_code(st2, _store(), "k", [("r", "a.py", CHUNK, {"bytes": KB4})], [])
    assert st2["savings_by_user"] == {}


def test_corrupt_nested_coerced():
    st = {"savings_by_repo": [], "savings_by_user": "x", "tokens_observed_code": None}
    savings.record_code(st, _store(), "k", [("r", "a.py", CHUNK, {"bytes": KB4})], [], user="u")
    assert st["savings_by_repo"]["r"]["observed"] == 900
    assert st["tokens_observed_code"] == 900
    st = {"savings_by_repo": {"r": 5}}
    savings.record_code(st, _store(), "k", [("r", "a.py", CHUNK, {"bytes": KB4})], [])
    assert st["savings_by_repo"]["r"]["hits"] == 1


def test_record_notes():
    st, s = {}, _store()
    savings.record_notes(st, s, "k", [("n/a.md", CHUNK), ("n/b.md", CHUNK)], {"n/a.md": KB4}, user="u")
    savings.record_notes(st, s, "k", [("n/a.md", CHUNK)], {"n/a.md": KB4}, user="u")
    assert st["tokens_observed_notes"] == 900
    assert st["savings_hits_unmeasured"] == 1
    assert st["savings_by_repo"]["notes"]["hits"] == 2


def test_notes_bytes_map_mtime_reload():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph_notes.json")
        with open(p, "w") as f:
            json.dump({"nodes": [{"id": "a\\b.md", "bytes": 10}, {"id": "c.md"}]}, f)
        os.utime(p, (1000, 1000))
        assert savings.notes_bytes_map(p) == {"a/b.md": 10}
        with open(p, "w") as f:
            json.dump({"nodes": [{"id": "z.md", "bytes": 5}]}, f)
        os.utime(p, (1000, 1000))
        assert savings.notes_bytes_map(p) == {"a/b.md": 10}  # same mtime: cached
        os.utime(p, (2000, 2000))
        assert savings.notes_bytes_map(p) == {"z.md": 5}
        assert savings.notes_bytes_map(os.path.join(d, "missing.json")) == {}


def test_totals_trend_ledger_snapshot():
    st = {"tokens_observed_code": 10, "tokens_observed_notes": 5, "tokens_modeled_code": 1,
          "savings_by_user": {"a": {"observed": 1, "modeled": 0}, "b": {"observed": 5, "modeled": 5}}}
    assert savings.totals(st) == (10, 5, 1, 16)
    assert savings.trend({"3.10.0": st, "3.2.0": {}}) == [("3.2.0", 0), ("3.10.0", 16)]
    assert savings.user_ledger(st) == [("b", 10), ("a", 1)]
    snap = savings.snapshot(st)
    snap["savings_by_user"]["a"]["observed"] = 99
    assert st["savings_by_user"]["a"]["observed"] == 1


def test_fmt_stats_line():
    old = formatters.fmt_stats("3.0.2", {"search_code_calls": 1, "search_notes_calls": 0, "graph_cache_hits": 0, "graph_cache_misses": 0})
    assert "tokens avoided: observed=0" in old
    assert "by user:" not in old
    st = {"search_notes_calls": 0, "graph_cache_hits": 0, "graph_cache_misses": 0, "tokens_observed_code": 2500, "savings_hits_measured": 3,
          "savings_by_user": {"a": {"observed": 12000, "modeled": 0}, "b": {"observed": 3000, "modeled": 0}}}
    out = formatters.fmt_stats("3.1.0", st, current=True)
    assert "observed=2k (code=2k notes=0)" in out
    assert "hits measured=3 unmeasured=0" in out
    assert "by user: a=12k b=3k" in out
    many = {"search_notes_calls": 0, "graph_cache_hits": 0, "graph_cache_misses": 0, "savings_by_user": {f"u{i}": {"observed": 1000 * (i + 1)} for i in range(7)}}
    assert "+2 more" in formatters.fmt_stats("v", many)


def test_fmt_status_and_classify():
    out = formatters.fmt_status("no_match", None, "x()")
    assert out.split("\n")[0] == "status: no_match"
    assert out.endswith("next: x()")
    assert formatters.fmt_status("index_missing", "h", "n") == "status: index_missing\nh\nnext: n"
    c = formatters.classify_empty
    assert c(False, 0, True) == "reindex_in_progress"
    assert c(True, 0, True) == "reindex_in_progress"
    assert c(True, 5, True) == "no_match"
    assert c(False, 0, False) == "index_missing"
    assert c(True, 0, False) == "index_empty"
    assert c(True, 5, False) == "no_match"


def test_graph_carries_bytes():
    try:
        import networkx  # noqa: F401
    except ImportError:
        print("skip graph bytes (no networkx)")
        return
    from pathlib import Path
    import code_graph
    import notes_graph
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "a.py").write_text("import b\n")
        (root / "b.py").write_text("x = 1\n")
        G = code_graph.build_code_graph(root, {"a.py", "b.py"})
        assert G.nodes["a.py"]["bytes"] == 9
        meta = code_graph.compute_code_metadata(G)
        assert meta["b.py"]["bytes"] == 6
        G2 = code_graph.build_code_graph(root, {"a.py", "gone.py"})
        assert "bytes" not in G2.nodes["gone.py"]
        assert "bytes" not in code_graph.compute_code_metadata(G2)["gone.py"]
        (root / "sub").mkdir()
        (root / "sub" / "n.md").write_text("hello [[m]]")
        (root / "m.md").write_text("m")
        NG = notes_graph.build_notes_graph(root)
        assert NG.nodes["sub/n.md"]["bytes"] == 11
        out = root / "out"
        notes_graph.persist_notes_graph(NG, out)
        nodes = {n["id"]: n for n in json.loads((out / "graph_notes.json").read_text())["nodes"]}
        assert nodes["m.md"]["bytes"] == 1


def test_tui_renderable():
    try:
        import rich  # noqa: F401
    except ImportError:
        print("skip tui (no rich)")
        return
    from rich.console import Console
    from cortex import tui
    for stats in ({}, {"search_code_calls": 3}):
        c = Console(record=True, width=100, file=io.StringIO())
        c.print(tui.build_renderable("3.1.0", stats, {}))
        assert "tokens avoided" in c.export_text()
    st = {"tokens_observed_code": 900, "tokens_modeled_code": 500, "savings_hits_unmeasured": 2,
          "savings_by_repo": {"r": {"observed": 900, "modeled": 500, "hits": 1}}}
    c = Console(record=True, width=120, file=io.StringIO())
    c.print(tui.build_renderable("3.1.0", st, {"3.0.2": {}}))
    text = c.export_text()
    assert "reindex to measure" in text and "1.4k" in text


def test_fmt_stats_by_repo_line():
    st = {"search_notes_calls": 0, "graph_cache_hits": 0, "graph_cache_misses": 0,
          "savings_by_repo": {"b": {"observed": 1000, "modeled": 0}, "a": {"observed": 12000, "modeled": 1000}},
          "savings_by_user": {"u": {"observed": 5000, "modeled": 0}}}
    out = formatters.fmt_stats("3.1.1", st)
    assert "  by repo: a=13k b=1k" in out
    assert out.index("by repo:") < out.index("by user:")
    assert "by repo:" not in formatters.fmt_stats("3.1.1", {"search_notes_calls": 0, "graph_cache_hits": 0, "graph_cache_misses": 0})


def test_cache_roundtrip_atomic():
    import cache
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "embed_cache.json")
        from pathlib import Path
        p = Path(f)
        cache.save_cache("code", {"r/a.py": {"mtime": 1.5, "hash": "abc"}}, p)
        cache.save_cache("notes", {"n.md": {"mtime": 2.0, "hash": "def"}}, p)
        assert cache.load_cache("code", p) == {"r/a.py": {"mtime": 1.5, "hash": "abc"}}
        assert cache.load_cache("notes", p) == {"n.md": {"mtime": 2.0, "hash": "def"}}
        assert sorted(os.listdir(d)) == ["embed_cache.json"]


def test_cache_corrupt_warns_and_returns_empty():
    import cache
    import unittest
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "embed_cache.json"
        p.write_text('{"code": {"r/a.py": {"mtime": 1.5, "hash"')  # truncated
        with unittest.TestCase().assertLogs("cortex.cache", level="WARNING") as cm:
            assert cache.load_cache("code", p) == {}
        assert str(p) in cm.output[0] and "re-embedded" in cm.output[0]
        assert cache.load_cache("code", Path(d) / "missing.json") == {}


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
