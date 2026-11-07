"""Multi-user server wiring: per-call user binding through CortexMCP.call_tool, admin-only tools,
workspace isolation, HTTP middleware, webhook fan-out, reindex notes guard. No network, no Qdrant."""

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp()
os.environ["REPOS_CONFIG"] = os.path.join(_TMP, "repos.json")
os.environ["ADMIN_PASSWORD"] = "admin-secret-pw"
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:9")  # unreachable on purpose
os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:9")
_root = os.path.join(os.path.dirname(__file__), "..")
sys.path[:0] = [os.path.join(_root, "server", "mcp"), os.path.join(_root, "core")]

import users  # noqa: E402
import oauth  # noqa: E402
import state  # noqa: E402
import reindex  # noqa: E402
import routes  # noqa: E402
from tools import mcp  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402

ASSERT_MSG = "expected PermissionError"


def _token_for(user: str | None) -> str:
    tok = f"tok-{user or 'legacy'}"
    entry = {"client_id": "test", "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    if user:
        entry["user"] = user
    oauth._store["tokens"][tok] = entry
    return tok


def _ctx(token: str):
    req = SimpleNamespace(headers=Headers({"authorization": f"Bearer {token}"}))
    return SimpleNamespace(request_context=SimpleNamespace(request=req))


def _call(name: str, args: dict, token: str) -> str:
    res = asyncio.run(mcp.call_tool(name, args, _ctx(token)))
    content = res.content if hasattr(res, "content") else res
    return "\n".join(getattr(c, "text", str(c)) for c in content)


def _setup():
    try:
        os.remove(users.users_file())
    except FileNotFoundError:
        pass
    users.create_workspace("proj", "alice/proj-wiki")
    tok, _ = users.create_invite("bob", ["proj"])
    users.accept_invite(tok, "bobs-long-password")
    return _token_for("bob"), _token_for("admin")


def test_tool_sees_calling_user():
    bob, admin = _setup()
    out = _call("whoami", {}, bob)
    assert "User: bob (member)" in out and "Active workspace: proj" in out, out
    out = _call("whoami", {}, admin)
    assert "User: admin (admin)" in out and "Active workspace: default" in out, out
    assert state.current_user() is None  # nothing leaks out of the call


def test_legacy_token_is_admin():
    _setup()
    out = _call("whoami", {}, _token_for(None))
    assert "User: admin" in out, out


def test_unauthenticated_and_admin_only_rejected():
    bob, _ = _setup()
    for name, args, tok in [("whoami", {}, "bogus"), ("list_users", {}, bob), ("clear_cache", {}, bob),
                            ("invite_user", {"username": "eve", "workspaces": ["proj"]}, bob)]:
        try:
            _call(name, args, tok)
            raise AssertionError(f"{ASSERT_MSG} for {name}")
        except PermissionError:
            pass


def test_member_cannot_switch_to_default():
    bob, _ = _setup()
    out = _call("switch_workspace", {"name": "default"}, bob)
    assert "don't have access" in out, out
    out = _call("switch_workspace", {"name": "../etc"}, bob)
    assert "Invalid workspace" in out, out


def test_admin_invite_tool_returns_link():
    _, admin = _setup()
    out = _call("invite_user", {"username": "carol", "workspaces": ["proj"]}, admin)
    assert "/invite/" in out and "single use" in out, out
    out = _call("list_users", {}, admin)
    assert "bob: proj" in out and "carol" in out, out


def test_removed_user_token_dies():
    bob, admin = _setup()
    _call("remove_user", {"username": "bob"}, admin)
    assert oauth.token_user(bob) is None


def test_member_without_workspace_never_falls_back_to_default():
    bob, _ = _setup()
    users.revoke("bob", "proj")
    tokens = state.bind_request("bob")
    try:
        try:
            state.get_active_workspace()
            raise AssertionError(ASSERT_MSG)
        except PermissionError:
            pass
    finally:
        state.unbind_request(tokens)


def test_middleware_blocks_member_dashboard_api():
    bob, admin = _setup()
    from middleware import _BearerTokenMiddleware
    seen = {}

    async def app(scope, receive, send):
        seen["user"], seen["ws"] = state.current_user(), state.get_active_workspace()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def run(path, token):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.request", "body": b""}

        scope = {"type": "http", "path": path, "method": "GET",
                 "headers": [(b"authorization", f"Bearer {token}".encode())]}
        asyncio.run(_BearerTokenMiddleware(app)(scope, receive, send))
        return sent[0]["status"]

    assert run("/api/stats", bob) == 403
    assert run("/api/me", bob) == 200 and seen == {"user": "bob", "ws": "proj"}
    assert run("/api/stats", admin) == 200 and seen == {"user": "admin", "ws": "default"}
    assert run("/api/stats", "bogus") == 401


def test_webhook_targets_fan_out():
    _setup()
    from repos import _save_repos
    _save_repos(["alice/game"], "proj")
    _save_repos(["Xoudusz/cortex", "alice/game"], "default")
    code_ws, wiki_ws = routes._webhook_targets("alice/game")
    assert code_ws == ["default", "proj"] and wiki_ws == [], (code_ws, wiki_ws)
    code_ws, wiki_ws = routes._webhook_targets("alice/proj-wiki")
    assert code_ws == [] and wiki_ws == ["proj"], (code_ws, wiki_ws)


def test_new_workspace_does_not_inherit_default_repos():
    _setup()
    from repos import _load_repos, ensure_workspace_repos
    users.create_workspace("fresh")
    assert _load_repos("fresh") == []
    ensure_workspace_repos("fresh")
    assert _load_repos("fresh") == []


def test_notes_reindex_in_shared_ws_never_reads_vault():
    _setup()
    calls = []
    orig_stream, orig_sync = reindex._stream, reindex._sync_wiki
    reindex._stream = lambda cmd, label, timeout, notes_path="": calls.append((cmd, notes_path))
    reindex._sync_wiki = lambda ws, repo: None  # clone failed
    tok = state.bind_workspace("proj")
    try:
        reindex._run_reindex(True, False)
        assert calls == [], calls  # wiki unavailable -> notes skipped, vault untouched
        users.set_wiki("proj", "")
        reindex._run_reindex(True, False)
        assert calls == [] and any("no wiki repo" in l for l in reindex._reindex_state["output"])
        reindex._sync_wiki = lambda ws, repo: __import__("pathlib").Path("/tmp/wiki-proj")
        users.set_wiki("proj", "alice/proj-wiki")
        reindex._run_reindex(True, False)
        assert calls == [(["/app/index.py"], "/tmp/wiki-proj")], calls
    finally:
        state.unbind_workspace(tok)
        reindex._stream, reindex._sync_wiki = orig_stream, orig_sync


def test_enqueue_captures_workspace():
    bob, _ = _setup()
    tokens = state.bind_request("bob")
    try:
        reindex._enqueue(False, True, "game")
    finally:
        state.unbind_request(tokens)
    job = reindex._job_queue.pop()
    assert job["ws"] == "proj", job


def test_git_auth_header_keeps_token_out_of_url():
    args = reindex._git_auth_args("ghp_secret")
    assert args[0] == "-c" and "extraheader=AUTHORIZATION: basic" in args[1] and "ghp_secret" not in args[1]
    assert reindex._git_auth_args("") == []


def test_indexers_skip_symlinks_out_of_root():
    from pathlib import Path
    from chunker import is_safe_file
    root = Path(tempfile.mkdtemp())
    secret_dir = Path(tempfile.mkdtemp())
    (secret_dir / "users.md").write_text("secret")
    (root / "ok.md").write_text("fine")
    (root / "leak.md").symlink_to(secret_dir / "users.md")
    (root / "dirlink").symlink_to(secret_dir, target_is_directory=True)
    assert is_safe_file(root / "ok.md", root)
    assert not is_safe_file(root / "leak.md", root)
    assert not is_safe_file(root / "dirlink" / "users.md", root)  # file reached through a symlinked dir
    assert not is_safe_file(root / "missing.md", root)


def test_throttle_ignores_spoofed_forwarded_for():
    def req(peer, xff=""):
        h = {"x-forwarded-for": xff} if xff else {}
        return SimpleNamespace(client=SimpleNamespace(host=peer), headers=Headers(h))
    # (public peer: 8.8.8.8 — Python counts the RFC 5737 documentation ranges as is_private)
    assert oauth._client_ip(req("8.8.8.8", "1.1.1.1")) == "8.8.8.8"  # direct client can't spoof
    assert oauth._client_ip(req("172.18.0.5", "6.6.6.6, 198.51.100.7")) == "198.51.100.7"  # rightmost hop from proxy
    assert oauth._client_ip(req("127.0.0.1")) == "127.0.0.1"


def test_throttle_per_username_across_ips():
    oauth._fails.clear()
    for i in range(oauth._FAIL_LIMITS["user"]):
        oauth._record_fail(f"198.51.100.{i}", "admin")
    assert oauth._throttled("203.0.113.1", "admin")  # fresh IP, same target user
    assert not oauth._throttled("203.0.113.1", "bob")
    oauth._fails.clear()


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
