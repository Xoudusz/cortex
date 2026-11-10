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


def test_throttle_per_username_slows_but_never_locks_out():
    oauth._fails.clear()
    for i in range(oauth._FAIL_LIMITS["user"]):
        oauth._record_fail(f"198.51.100.{i}", "admin")
    assert oauth._user_slowed("admin")  # distributed guessing gets slowed down...
    assert not oauth._throttled("8.8.4.4", "admin")  # ...but the real admin from a fresh IP isn't blocked
    assert not oauth._user_slowed("bob")
    assert oauth._user_delay("admin") == 3.0
    for i in range(40):
        oauth._record_fail("9.9.9.9", "admin")
    assert oauth._user_delay("admin") == 30.0  # 3 * 2**4 = 48 -> capped
    oauth._fails.clear()


def _slowed_attempts(username: str, ips: list) -> tuple:
    """Fire parallel login attempts for a slowed username; return (statuses, elapsed seconds)."""
    import time as _t
    oauth._fails.clear()
    oauth._user_locks.clear()
    for i in range(oauth._FAIL_LIMITS["user"]):
        oauth._record_fail(f"10.1.0.{i}", username)
    saved = oauth._USER_DELAY
    oauth._USER_DELAY = 0.3

    async def _aw(v):
        return v

    async def attempt(ip):
        form = {"username": username, "password": "wrong", "client_id": "c", "redirect_uri": "https://e/cb",
                "code_challenge": "x", "code_challenge_method": "S256", "state": ""}
        req = SimpleNamespace(form=lambda: _aw(form), client=SimpleNamespace(host=ip), headers=Headers({}))
        return (await oauth.authorize_post(req)).status_code

    async def main():
        return await asyncio.gather(*(attempt(ip) for ip in ips))

    t0 = _t.time()
    try:
        statuses = asyncio.run(main())
    finally:
        oauth._USER_DELAY = saved
        oauth._fails.clear()
        oauth._user_locks.clear()
    return statuses, _t.time() - t0


def test_parallel_attempts_same_ip_get_429_not_a_queue():
    statuses, elapsed = _slowed_attempts("admin", ["8.8.1.1"] * 3)
    assert sorted(statuses) == [400, 429, 429], statuses  # one runs (wrong pw), the rest rejected at once
    assert elapsed < 0.9, f"attempts queued ({elapsed:.2f}s)"


def test_attacker_ip_does_not_delay_other_ips():
    statuses, elapsed = _slowed_attempts("admin", ["8.8.1.1", "8.8.2.2"])
    assert statuses == [400, 400], statuses
    assert elapsed < 0.6, f"second IP waited behind the first ({elapsed:.2f}s)"


def test_unknown_user_gets_same_delay():
    _, elapsed = _slowed_attempts("nobody-here", ["8.8.3.3"])
    assert elapsed >= 0.3, f"unknown user skipped the delay ({elapsed:.2f}s)"


def test_untrusted_private_peer_cannot_spoof_when_proxies_pinned():
    saved = oauth.TRUSTED_PROXIES
    oauth.TRUSTED_PROXIES = [__import__("ipaddress").ip_network("172.18.0.2/32")]
    try:
        r = SimpleNamespace(client=SimpleNamespace(host="192.168.68.50"), headers=Headers({"x-forwarded-for": "1.2.3.4"}))
        assert oauth._client_ip(r) == "192.168.68.50"
        r = SimpleNamespace(client=SimpleNamespace(host="172.18.0.2"), headers=Headers({"x-forwarded-for": "1.2.3.4"}))
        assert oauth._client_ip(r) == "1.2.3.4"
    finally:
        oauth.TRUSTED_PROXIES = saved


def test_dashboard_workspace_header_binds_admin_ws():
    bob, admin = _setup()
    from middleware import _BearerTokenMiddleware
    seen = {}

    async def app(scope, receive, send):
        seen["ws"] = state.get_active_workspace()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def run(path, token, extra=()):
        sent = []

        async def send(msg):
            sent.append(msg)

        async def receive():
            return {"type": "http.request", "body": b""}

        scope = {"type": "http", "path": path, "method": "GET",
                 "headers": [(b"authorization", f"Bearer {token}".encode()), *extra]}
        asyncio.run(_BearerTokenMiddleware(app)(scope, receive, send))
        return sent[0]["status"]

    assert run("/api/stats", admin, [(b"x-cortex-workspace", b"proj")]) == 200 and seen["ws"] == "proj"
    assert run("/api/stats", admin, [(b"x-cortex-workspace", b"nope")]) == 200 and seen["ws"] == "default"
    assert run("/api/stats", admin) == 200 and seen["ws"] == "default"
    assert run("/api/stats", admin, [(b"x-cortex-workspace", b"default")]) == 200 and seen["ws"] == "default"
    assert run("/api/users", bob, [(b"x-cortex-workspace", b"proj")]) == 403


def test_repo_check_rejects_bad_format_without_network():
    _setup()
    from starlette.requests import Request
    real = routes.httpx.AsyncClient

    def boom(*a, **k):
        raise AssertionError("network call attempted for an invalid repo")

    routes.httpx.AsyncClient = boom
    try:
        for q in (b"repo=not%20a%20repo", b"repo=../user", b"repo=owner/..", b"repo=.hidden/x"):
            req = Request({"type": "http", "method": "GET", "path": "/api/github/repo-check",
                           "query_string": q, "headers": []})
            resp = asyncio.run(routes._api_github_repo_check(req))
            assert resp.status_code == 400 and b"Use owner/name format" in resp.body, (q, resp.body)
    finally:
        routes.httpx.AsyncClient = real


def test_repo_check_branches():
    _setup()
    from starlette.requests import Request
    seen = {}

    class FakeResp:
        def __init__(self, status, body=None):
            self.status_code, self._body = status, body or {}

        def json(self):
            return self._body

    class FakeClient:
        status, body = 200, {}

        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            seen["url"], seen["auth"] = url, headers.get("Authorization")
            return FakeResp(FakeClient.status, FakeClient.body)

    def check(qs):
        req = Request({"type": "http", "method": "GET", "path": "/api/github/repo-check",
                       "query_string": qs.encode(), "headers": []})
        return asyncio.run(routes._api_github_repo_check(req))

    orig_client, orig_tok = routes.httpx.AsyncClient, routes.get_github_token
    routes.httpx.AsyncClient = FakeClient
    try:
        routes.get_github_token = lambda: ("", "none")
        r = check("repo=alice/app")
        assert r.status_code == 503 and b"No GitHub token configured" in r.body, r.body
        routes.get_github_token = lambda: ("ghp_tok", "settings")
        FakeClient.status, FakeClient.body = 200, {"full_name": "alice/app", "private": True, "archived": False}
        r = check("repo=https%3A%2F%2Fgithub.com%2Falice%2Fapp.git%2F")
        assert r.status_code == 200 and seen["url"] == "https://api.github.com/repos/alice/app", seen
        assert seen["auth"] == "token ghp_tok"
        import json as _json
        assert _json.loads(r.body) == {"exists": True, "full_name": "alice/app", "private": True, "archived": False}
        FakeClient.status = 404
        r = check("repo=alice/gone")
        assert r.status_code == 200 and _json.loads(r.body) == {"exists": False}, r.body
        FakeClient.status = 500
        r = check("repo=alice/app")
        assert r.status_code == 502 and b"500" in r.body, r.body
    finally:
        routes.httpx.AsyncClient, routes.get_github_token = orig_client, orig_tok


def test_webhook_targets_exact_owner_name():
    _setup()
    from repos import _save_repos
    _save_repos(["alice/app"], "default")
    _save_repos(["bob/app"], "proj")
    code_ws, _ = routes._webhook_targets("alice/app")
    assert code_ws == ["default"], code_ws  # bob/app must not match a push from alice/app
    code_ws, _ = routes._webhook_targets("ALICE/app")
    assert code_ws == ["default"], code_ws  # case-insensitive
    code_ws, _ = routes._webhook_targets("bob/app")
    assert code_ws == ["proj"], code_ws


def test_clone_dest_keyed_by_owner():
    from pathlib import Path
    sys.path.insert(0, os.path.join(_root, "server", "indexer"))
    import index_code
    assert index_code._clone_dest("alice/app") == index_code.REPOS_DIR / "alice" / "app"
    assert index_code._clone_dest("alice/app") != index_code._clone_dest("bob/app")
    assert isinstance(index_code._clone_dest("alice/app"), Path)


def test_api_stats_and_search_use_workspace_collections():
    _setup()
    import web_ui
    names = []

    class FakeQdrant:
        def __init__(self, url=None):
            pass

        def collection_exists(self, name):
            names.append(("exists", name))
            return False  # shared workspace not indexed yet

        def get_collection(self, name):
            raise AssertionError("must not fetch a missing collection")

        def query_points(self, name, **kw):
            names.append(("query", name))
            return SimpleNamespace(points=[])

    class FakeReq:
        async def json(self):
            return {"query": "hello", "collections": ["notes", "code"]}

    orig_qc, orig_get = web_ui.QdrantClient, web_ui.httpx.get
    web_ui.QdrantClient = FakeQdrant
    def no_ollama(*a, **k):
        raise OSError("no ollama in tests")

    web_ui.httpx.get = no_ollama
    tok = state.bind_workspace("proj")
    try:
        stats = asyncio.run(web_ui.api_stats(None, "http://qdrant", "http://ollama"))
        assert stats.body and b'"notes":{"points_count":0}' in stats.body and b'"code":{"points_count":0}' in stats.body, stats.body
        res = asyncio.run(web_ui.api_search(FakeReq(), "http://qdrant", lambda q: [0.0]))
        assert res.body == b'{"notes":[],"code":[]}', res.body
    finally:
        state.unbind_workspace(tok)
        web_ui.QdrantClient, web_ui.httpx.get = orig_qc, orig_get
    assert ("exists", "proj_notes") in names and ("exists", "proj_code") in names, names
    assert ("query", "proj_notes") in names and ("query", "proj_code") in names, names


def test_template_pkce_and_switcher():
    import template  # noqa: E402
    html = template.UI_HTML
    # per-login PKCE verifier keyed by state, so concurrent tabs do not clobber each other
    assert "cortex_pkce_" in html
    assert "state: state" in html
    assert "setItem('cortex_pkce_verifier'" not in html
    # header workspace switcher and scoped API calls
    assert 'id="ws-switch"' in html
    assert "X-Cortex-Workspace" in html
    assert "/api/github/repo-check" in html
    # invite picks its workspace from the switcher, no per-invite checkboxes
    assert 'id="invite-ws"' not in html


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
