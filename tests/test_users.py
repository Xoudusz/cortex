"""Multi-user store (server/mcp/users.py) — no network, no Qdrant."""

import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp()
os.environ["REPOS_CONFIG"] = os.path.join(_TMP, "repos.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server", "mcp"))

import users  # noqa: E402

ADMIN_PW = "admin-secret-pw"


def _reset():
    try:
        os.remove(users.users_file())
    except FileNotFoundError:
        pass


def test_password_hash_roundtrip_owasp_params():
    h = users.hash_password("correct horse battery")
    assert h.startswith("scrypt$131072$8$1$")  # N=2^17, r=8, p=1
    assert users.verify_password("correct horse battery", h)
    assert not users.verify_password("wrong", h)
    assert users.hash_password("x" * 12) != users.hash_password("x" * 12)  # salted


def test_admin_login_uses_env_password():
    _reset()
    assert users.check_login("admin", ADMIN_PW, ADMIN_PW)
    assert users.check_login("Admin", ADMIN_PW, ADMIN_PW)
    assert not users.check_login("admin", "nope", ADMIN_PW)
    assert not users.check_login("admin", "", "")  # auth not configured -> never valid


def test_names_validated():
    assert users.valid_name("proj-1") and users.valid_name("bob")
    for bad in ["", "a", "../etc", "Bob", "with space", "x" * 40, "a/b"]:
        assert not users.valid_name(bad), bad
    assert users.create_workspace("default")
    assert users.create_workspace("../x")


def test_invite_flow_single_use():
    _reset()
    assert users.create_workspace("proj", "alice/proj-wiki") == ""
    token, err = users.create_invite("bob", ["proj"])
    assert not err and len(token) >= 40
    raw = users.users_file().read_text()
    assert token not in raw  # only the hash is stored
    assert users.invite_info(token)["username"] == "bob"

    name, err = users.accept_invite(token, "short")
    assert not name and "at least" in err
    name, err = users.accept_invite(token, "bobs-long-password")
    assert name == "bob" and not err
    name, err = users.accept_invite(token, "bobs-long-password")
    assert not name and err  # single use
    assert users.check_login("bob", "bobs-long-password", ADMIN_PW)
    assert not users.check_login("bob", "wrong-password", ADMIN_PW)
    assert users.user_workspaces("bob") == ["proj"]


def test_invite_expiry():
    _reset()
    users.create_workspace("proj")
    token, _ = users.create_invite("carol", ["proj"])
    data = json.loads(users.users_file().read_text())
    for inv in data["invites"].values():
        inv["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    users.users_file().write_text(json.dumps(data))
    assert users.invite_info(token) is None
    name, err = users.accept_invite(token, "carols-long-password")
    assert not name and "expired" in err


def test_default_workspace_never_shareable():
    _reset()
    users.create_workspace("proj")
    _, err = users.create_invite("dave", ["default"])
    assert "private" in err
    token, _ = users.create_invite("dave", ["proj"])
    users.accept_invite(token, "daves-long-password")
    assert "private" in users.grant("dave", "default")
    assert not users.can_access("dave", "default")
    assert users.can_access("admin", "default")


def test_grant_revoke_active_ws():
    _reset()
    users.create_workspace("proj")
    users.create_workspace("other")
    token, _ = users.create_invite("erin", ["proj"])
    users.accept_invite(token, "erins-long-password")
    assert users.get_active_ws("erin") == "proj"
    assert users.grant("erin", "other") == ""
    users.set_active_ws("erin", "other")
    assert users.get_active_ws("erin") == "other"
    users.revoke("erin", "other")
    assert users.get_active_ws("erin") == "proj"
    users.revoke("erin", "proj")
    assert users.get_active_ws("erin") is None
    assert users.get_active_ws("admin") == "default"


def test_remove_user_and_delete_workspace():
    _reset()
    users.create_workspace("proj")
    token, _ = users.create_invite("finn", ["proj"])
    users.accept_invite(token, "finns-long-password")
    assert users.delete_workspace("proj") == ""
    assert users.user_workspaces("finn") == []
    assert users.remove_user("finn")
    assert not users.exists("finn")
    assert not users.check_login("finn", "finns-long-password", ADMIN_PW)


def test_file_is_private():
    _reset()
    users.create_workspace("proj")
    mode = stat.S_IMODE(os.stat(users.users_file()).st_mode)
    assert mode == 0o600, oct(mode)


def test_wiki_repo_validation():
    _reset()
    assert users.create_workspace("proj", "not a repo")
    assert users.create_workspace("proj", "owner/wiki") == ""
    assert users.get_wiki("proj") == "owner/wiki"
    assert users.set_wiki("proj", "") == "" and users.get_wiki("proj") == ""


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
