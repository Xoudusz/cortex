#!/usr/bin/env python3
"""Users, invites and the shared-workspace registry for cortex-mcp (multi-user server mode).

Storage is a single JSON file (DATA_DIR/users.json, mode 0600) — no database:
    {
      "users":      {name: {"pw": "scrypt$...", "workspaces": [ws, ...], "active_ws": ws, "created_at": iso}},
      "invites":    {sha256(token): {"username", "workspaces", "expires_at", "created_by"}},
      "workspaces": {name: {"wiki_repo": "owner/name" | "", "created_at": iso}},
    }

The admin is not stored with a password: user "admin" always authenticates against the
ADMIN_PASSWORD env var (so rotating it in Portainer keeps working) and can access every workspace.
"default" is the admin's private workspace (personal vault + repos) and can never be granted.

Security choices (OWASP Password Storage / Authentication cheat sheets):
- passwords: hashlib.scrypt N=2^17, r=8, p=1, 16-byte salt, constant-time compare
- invite links: 256-bit random token, only its SHA-256 is stored, 7-day expiry, single use
- unknown user still runs one scrypt so response timing doesn't reveal which usernames exist
"""

import base64
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ADMIN = "admin"
DEFAULT_WS = "default"
INVITE_TTL = timedelta(days=7)
MIN_PASSWORD = 10
MAX_PASSWORD = 256

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 17, 8, 1
_SCRYPT_MAXMEM = 256 * 1024 * 1024  # N=2^17,r=8 needs 128 MiB; hashlib's default cap is 32 MiB
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_lock = threading.RLock()


def _data_dir() -> Path:
    return Path(os.environ.get("REPOS_CONFIG", "/app/data/repos.json")).parent


def users_file() -> Path:
    return _data_dir() / "users.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _empty() -> dict:
    return {"users": {}, "invites": {}, "workspaces": {}}


def _load() -> dict:
    try:
        data = json.loads(users_file().read_text())
        return {**_empty(), **data}
    except FileNotFoundError:
        return _empty()


def _save(data: dict) -> None:
    path = users_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# --- validation ---------------------------------------------------------------

def valid_name(name: str) -> bool:
    """Usernames and workspace names: lowercase, 2-32 chars. Also used as path + collection parts."""
    return bool(name) and bool(_NAME_RE.match(name))


def valid_repo(repo: str) -> bool:
    return bool(repo) and bool(_REPO_RE.match(repo))


def password_problem(pw: str) -> str:
    if len(pw) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(pw) > MAX_PASSWORD:
        return f"Password must be at most {MAX_PASSWORD} characters."
    return ""


# --- passwords -----------------------------------------------------------------

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                        maxmem=_SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(dk)}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk)
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=_SCRYPT_MAXMEM, dklen=len(expected))
        return secrets.compare_digest(got, expected)
    except Exception:
        return False


_DUMMY_HASH = ""


def check_login(username: str, password: str, admin_password: str) -> bool:
    """True if the credentials are valid. Admin checks against the ADMIN_PASSWORD env value."""
    global _DUMMY_HASH
    username = (username or "").strip().lower()
    if username == ADMIN:
        return bool(admin_password) and secrets.compare_digest(password.encode(), admin_password.encode())
    with _lock:
        user = _load()["users"].get(username)
    if not user:
        if not _DUMMY_HASH:
            _DUMMY_HASH = hash_password(secrets.token_hex(8))
        verify_password(password, _DUMMY_HASH)  # equalize timing for unknown users
        return False
    return verify_password(password, user.get("pw", ""))


# --- users ---------------------------------------------------------------------

def exists(username: str) -> bool:
    if username == ADMIN:
        return True
    with _lock:
        return username in _load()["users"]


def is_admin(username: str | None) -> bool:
    return username == ADMIN


def list_users() -> list[dict]:
    with _lock:
        data = _load()
    out = [{"username": ADMIN, "admin": True, "workspaces": ["*"]}]
    for name, u in sorted(data["users"].items()):
        out.append({"username": name, "admin": False, "workspaces": sorted(u.get("workspaces", [])),
                    "created_at": u.get("created_at", "")})
    return out


def remove_user(username: str) -> bool:
    with _lock:
        data = _load()
        if username not in data["users"]:
            return False
        del data["users"][username]
        data["invites"] = {h: i for h, i in data["invites"].items() if i.get("username") != username}
        _save(data)
    return True


def _check_shareable(data: dict, ws: str) -> str:
    if ws == DEFAULT_WS:
        return "The 'default' workspace is private to the admin and can't be shared."
    if ws not in data["workspaces"]:
        return f"Unknown workspace '{ws}'. Create it first."
    return ""


def grant(username: str, ws: str) -> str:
    """Grant username access to ws. Returns an error message, or '' on success."""
    with _lock:
        data = _load()
        if username not in data["users"]:
            return f"Unknown user '{username}'."
        err = _check_shareable(data, ws)
        if err:
            return err
        wss = data["users"][username].setdefault("workspaces", [])
        if ws not in wss:
            wss.append(ws)
        _save(data)
    return ""


def revoke(username: str, ws: str) -> str:
    with _lock:
        data = _load()
        user = data["users"].get(username)
        if not user:
            return f"Unknown user '{username}'."
        user["workspaces"] = [w for w in user.get("workspaces", []) if w != ws]
        if user.get("active_ws") == ws:
            user["active_ws"] = ""
        _save(data)
    return ""


def user_workspaces(username: str | None) -> list[str]:
    """Workspaces the user may use. Admin: default + every registered workspace."""
    if not username:
        return []
    with _lock:
        data = _load()
    if is_admin(username):
        return [DEFAULT_WS] + sorted(data["workspaces"])
    user = data["users"].get(username)
    if not user:
        return []
    return [w for w in user.get("workspaces", []) if w in data["workspaces"]]


def can_access(username: str | None, ws: str) -> bool:
    if is_admin(username):
        return True  # admin may also use legacy workspaces that predate the registry
    return ws in user_workspaces(username)


def get_active_ws(username: str | None) -> str | None:
    """The user's remembered workspace if still accessible, else their first one (None if none)."""
    if not username:
        return None
    with _lock:
        data = _load()
    stored = (data["users"].get(username) or {}).get("active_ws", "") if not is_admin(username) \
        else data.get("admin_active_ws", "")
    if stored and can_access(username, stored):
        return stored
    wss = user_workspaces(username)
    return wss[0] if wss else None


def set_active_ws(username: str, ws: str) -> None:
    with _lock:
        data = _load()
        if is_admin(username):
            data["admin_active_ws"] = ws
        elif username in data["users"]:
            data["users"][username]["active_ws"] = ws
        else:
            return
        _save(data)


# --- invites -------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invite(username: str, workspaces: list[str], created_by: str = ADMIN) -> tuple[str, str]:
    """Return (token, error). The plaintext token exists only in the returned link."""
    username = (username or "").strip().lower()
    if not valid_name(username) or username == ADMIN:
        return "", "Username must be 2-32 chars: lowercase letters, digits, '-' or '_' (not 'admin')."
    with _lock:
        data = _load()
        if username in data["users"]:
            return "", f"User '{username}' already exists. Use grant_workspace to add workspaces."
        for ws in workspaces:
            err = _check_shareable(data, ws)
            if err:
                return "", err
        now = _now()
        data["invites"] = {h: i for h, i in data["invites"].items() if i.get("expires_at", "") > now.isoformat()
                           and i.get("username") != username}  # purge expired + replace older invite
        token = secrets.token_urlsafe(32)
        data["invites"][_token_hash(token)] = {
            "username": username, "workspaces": list(dict.fromkeys(workspaces)),
            "expires_at": (now + INVITE_TTL).isoformat(), "created_by": created_by,
        }
        _save(data)
    return token, ""


def invite_info(token: str) -> dict | None:
    with _lock:
        inv = _load()["invites"].get(_token_hash(token or ""))
    if not inv or inv.get("expires_at", "") <= _now().isoformat():
        return None
    return dict(inv)


def accept_invite(token: str, password: str) -> tuple[str, str]:
    """Consume the invite and create the user. Returns (username, error)."""
    err = password_problem(password)
    if err:
        return "", err
    pw_hash = hash_password(password)  # slow: do it outside the lock
    with _lock:
        data = _load()
        h = _token_hash(token or "")
        inv = data["invites"].get(h)
        if not inv or inv.get("expires_at", "") <= _now().isoformat():
            return "", "This invite link is invalid or has expired. Ask for a new one."
        username = inv["username"]
        if username in data["users"]:
            del data["invites"][h]
            _save(data)
            return "", "This invite was already used."
        data["users"][username] = {
            "pw": pw_hash,
            "workspaces": [w for w in inv.get("workspaces", []) if w in data["workspaces"]],
            "active_ws": "",
            "created_at": _now().isoformat(),
        }
        del data["invites"][h]  # single use
        _save(data)
    return username, ""


def list_invites() -> list[dict]:
    now = _now().isoformat()
    with _lock:
        invites = _load()["invites"]
    return [{"username": i["username"], "workspaces": i.get("workspaces", []), "expires_at": i["expires_at"]}
            for i in invites.values() if i.get("expires_at", "") > now]


def revoke_invite(username: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["invites"])
        data["invites"] = {h: i for h, i in data["invites"].items() if i.get("username") != username}
        if len(data["invites"]) == before:
            return False
        _save(data)
    return True


# --- workspace registry (shared workspaces) -----------------------------------

def list_registered() -> dict:
    with _lock:
        return dict(_load()["workspaces"])


def create_workspace(name: str, wiki_repo: str = "") -> str:
    name = (name or "").strip().lower()
    wiki_repo = (wiki_repo or "").strip()
    if not valid_name(name) or name == DEFAULT_WS:
        return "Workspace name must be 2-32 chars: lowercase letters, digits, '-' or '_' (not 'default')."
    if wiki_repo and not valid_repo(wiki_repo):
        return "wiki_repo must be in owner/name format."
    with _lock:
        data = _load()
        if name in data["workspaces"]:
            return f"Workspace '{name}' already exists."
        data["workspaces"][name] = {"wiki_repo": wiki_repo, "created_at": _now().isoformat()}
        _save(data)
    return ""


def set_wiki(name: str, wiki_repo: str) -> str:
    wiki_repo = (wiki_repo or "").strip()
    if wiki_repo and not valid_repo(wiki_repo):
        return "wiki_repo must be in owner/name format."
    with _lock:
        data = _load()
        if name not in data["workspaces"]:
            return f"Unknown workspace '{name}'."
        data["workspaces"][name]["wiki_repo"] = wiki_repo
        _save(data)
    return ""


def get_wiki(name: str) -> str:
    with _lock:
        return (_load()["workspaces"].get(name) or {}).get("wiki_repo", "")


def delete_workspace(name: str) -> str:
    """Unregister a shared workspace and drop it from every user (index data is left on disk)."""
    with _lock:
        data = _load()
        if name not in data["workspaces"]:
            return f"Unknown workspace '{name}'."
        del data["workspaces"][name]
        for u in data["users"].values():
            u["workspaces"] = [w for w in u.get("workspaces", []) if w != name]
            if u.get("active_ws") == name:
                u["active_ws"] = ""
        for inv in data["invites"].values():
            inv["workspaces"] = [w for w in inv.get("workspaces", []) if w != name]
        if data.get("admin_active_ws") == name:
            data["admin_active_ws"] = ""
        _save(data)
    return ""
