"""OAuth 2.0 Authorization Server for Cortex.

Implements:
- RFC 8414: Authorization Server Metadata
- RFC 7591: Dynamic Client Registration
- RFC 7636: PKCE (S256 only)
- Authorization Code + Refresh Token grants (single-user, password-based)
"""
import base64
import hashlib
import json
import logging
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

log = logging.getLogger("cortex.oauth")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8765").rstrip("/")
_DATA_DIR = Path(os.environ.get("REPOS_CONFIG", "/app/data/repos.json")).parent
STATE_FILE = _DATA_DIR / "oauth_state.json"

CODE_TTL = timedelta(seconds=60)
TOKEN_TTL = timedelta(days=30)
REFRESH_TTL = timedelta(days=90)

_WEB_UI_CLIENT_ID = "cortex-web-ui"

_store: dict = {
    "clients": {},
    "codes": {},
    "tokens": {},
    "refresh_tokens": {},
}


def _iso(dt: datetime) -> str:
    """Format datetime as UTC ISO 8601 string."""
    return dt.astimezone(timezone.utc).isoformat()


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return _iso(datetime.now(timezone.utc))


def _load() -> None:
    """Load persisted OAuth state (clients, codes, tokens) from STATE_FILE into _store."""
    try:
        if STATE_FILE.exists():
            _store.update(json.loads(STATE_FILE.read_text()))
    except Exception as e:
        log.warning("[oauth] state load failed: %s", e)


def _save() -> None:
    """Persist _store to STATE_FILE as JSON."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(_store, indent=2))
    except Exception as e:
        log.warning("[oauth] state save failed: %s", e)


def _purge_expired() -> None:
    """Remove expired codes, access tokens, and refresh tokens from _store."""
    now = _now_iso()
    for key in ("codes", "tokens", "refresh_tokens"):
        _store[key] = {k: v for k, v in _store[key].items() if v.get("expires_at", "") > now}


def _ensure_web_ui_client() -> None:
    """Register the built-in web UI OAuth client, keeping its redirect_uri in sync with BASE_URL."""
    if _WEB_UI_CLIENT_ID not in _store["clients"]:
        _store["clients"][_WEB_UI_CLIENT_ID] = {
            "client_id": _WEB_UI_CLIENT_ID,
            "client_name": "Cortex Web UI",
            "redirect_uris": [BASE_URL + "/"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
    else:
        # Keep redirect_uri in sync with BASE_URL
        _store["clients"][_WEB_UI_CLIENT_ID]["redirect_uris"] = [BASE_URL + "/"]


_load()
_purge_expired()
_ensure_web_ui_client()


def verify_token(token: str) -> bool:
    """Return True if token exists in _store and has not expired."""
    entry = _store["tokens"].get(token)
    if not entry:
        return False
    return _now_iso() < entry.get("expires_at", "")


def _pkce_verify(verifier: str, challenge: str) -> bool:
    """Verify a PKCE S256 code_verifier against a stored code_challenge."""
    digest = hashlib.sha256(verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(computed, challenge)


# --- Request handlers ---

async def well_known_as(request: Request) -> JSONResponse:
    """RFC 8414: serve Authorization Server metadata at /.well-known/oauth-authorization-server."""
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": BASE_URL + "/authorize",
        "token_endpoint": BASE_URL + "/token",
        "registration_endpoint": BASE_URL + "/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    })


async def well_known_resource(request: Request) -> JSONResponse:
    """RFC 8414: serve Protected Resource metadata at /.well-known/oauth-protected-resource."""
    return JSONResponse({
        "resource": BASE_URL,
        "authorization_servers": [BASE_URL],
    })


async def register(request: Request) -> JSONResponse:
    """RFC 7591: Dynamic Client Registration — issue a new client_id."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    redirect_uris = body.get("redirect_uris", [])
    if not redirect_uris:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "redirect_uris required"},
            status_code=400,
        )

    client_id = secrets.token_urlsafe(16)
    client = {
        "client_id": client_id,
        "client_name": body.get("client_name", ""),
        "redirect_uris": redirect_uris,
        "grant_types": body.get("grant_types", ["authorization_code"]),
        "response_types": body.get("response_types", ["code"]),
        "token_endpoint_auth_method": "none",
    }
    _store["clients"][client_id] = client
    _save()
    log.info("[oauth] registered client %s (%s)", client_id, client.get("client_name"))
    return JSONResponse(
        {**client, "client_id_issued_at": int(datetime.now(timezone.utc).timestamp())},
        status_code=201,
    )


_FORM_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cortex — Sign in</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #111318; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
.card { background: #1c2030; border: 1px solid #2d3248; border-radius: 12px; padding: 2rem; width: 100%; max-width: 360px; }
h1 { font-size: 1.1rem; font-weight: 700; background: linear-gradient(135deg, #c084fc, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 1.5rem; text-align: center; }
label { font-size: 0.8rem; color: #8896a8; display: block; margin-bottom: 0.4rem; }
input[type=password] { width: 100%; background: #111318; border: 1px solid #2d3248; border-radius: 6px; color: #e2e8f0; padding: 0.6rem 0.75rem; font-size: 0.9rem; outline: none; }
input[type=password]:focus { border-color: #a78bfa; }
button { width: 100%; margin-top: 1rem; background: #a78bfa; border: none; border-radius: 6px; color: #111318; font-weight: 700; padding: 0.65rem; cursor: pointer; font-size: 0.9rem; }
button:hover { background: #c084fc; }
.error { color: #f87171; font-size: 0.8rem; margin-top: 0.75rem; text-align: center; }
</style>
</head>
<body>
<div class="card">
  <h1>Cortex</h1>
  <form method="POST">
    <input type="hidden" name="client_id" value="__CLIENT_ID__">
    <input type="hidden" name="redirect_uri" value="__REDIRECT_URI__">
    <input type="hidden" name="code_challenge" value="__CODE_CHALLENGE__">
    <input type="hidden" name="code_challenge_method" value="__CODE_CHALLENGE_METHOD__">
    <input type="hidden" name="state" value="__STATE__">
    <label for="pw">Password</label>
    <input type="password" id="pw" name="password" autofocus autocomplete="current-password">
    <button type="submit">Sign in</button>
    __ERROR__
  </form>
</div>
</body>
</html>"""


def _render_form(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    error: str = "",
) -> str:
    error_html = f'<p class="error">{error}</p>' if error else ""
    return (
        _FORM_TEMPLATE
        .replace("__CLIENT_ID__", client_id)
        .replace("__REDIRECT_URI__", redirect_uri)
        .replace("__CODE_CHALLENGE__", code_challenge)
        .replace("__CODE_CHALLENGE_METHOD__", code_challenge_method)
        .replace("__STATE__", state)
        .replace("__ERROR__", error_html)
    )


async def authorize_get(request: Request) -> HTMLResponse | JSONResponse:
    """Render the PKCE authorization form; validate client_id, redirect_uri, and S256 challenge."""
    p = request.query_params
    response_type = p.get("response_type", "")
    client_id = p.get("client_id", "")
    redirect_uri = p.get("redirect_uri", "")
    code_challenge = p.get("code_challenge", "")
    code_challenge_method = p.get("code_challenge_method", "")
    state = p.get("state", "")

    if response_type != "code":
        return JSONResponse({"error": "unsupported_response_type"}, status_code=400)
    if not client_id or not redirect_uri or not code_challenge:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Missing required parameters"},
            status_code=400,
        )
    if code_challenge_method != "S256":
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Only S256 supported"},
            status_code=400,
        )

    client = _store["clients"].get(client_id)
    if client and redirect_uri not in client["redirect_uris"]:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "redirect_uri mismatch"},
            status_code=400,
        )

    return HTMLResponse(_render_form(client_id, redirect_uri, code_challenge, code_challenge_method, state))


async def authorize_post(request: Request) -> HTMLResponse | RedirectResponse | JSONResponse:
    """Validate password, issue auth code, and redirect to redirect_uri with code + state."""
    form = await request.form()
    password = form.get("password", "")
    client_id = form.get("client_id", "")
    redirect_uri = form.get("redirect_uri", "")
    code_challenge = form.get("code_challenge", "")
    code_challenge_method = form.get("code_challenge_method", "S256")
    state = form.get("state", "")

    def bad(msg: str) -> HTMLResponse:
        return HTMLResponse(
            _render_form(client_id, redirect_uri, code_challenge, code_challenge_method, state, msg),
            status_code=400,
        )

    if not ADMIN_PASSWORD:
        return bad("Auth not configured — set ADMIN_PASSWORD env var")

    if not secrets.compare_digest(password, ADMIN_PASSWORD):
        log.warning("[oauth] failed login attempt from %s", request.client)
        return bad("Incorrect password")

    code = secrets.token_hex(32)
    _store["codes"][code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "expires_at": _iso(datetime.now(timezone.utc) + CODE_TTL),
        "used": False,
    }
    _save()
    log.info("[oauth] issued auth code for client %s", client_id)

    sep = "&" if "?" in redirect_uri else "?"
    params = urllib.parse.urlencode({"code": code, **({"state": state} if state else {})})
    return RedirectResponse(redirect_uri + sep + params, status_code=302)


async def token_endpoint(request: Request) -> JSONResponse:
    """Issue access + refresh tokens for authorization_code grant, or rotate access token for refresh_token grant."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = dict(await request.json())
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
    else:
        form = await request.form()
        body = dict(form)

    grant_type = body.get("grant_type", "")

    if grant_type == "authorization_code":
        code = body.get("code", "")
        code_verifier = body.get("code_verifier", "")
        redirect_uri = body.get("redirect_uri", "")

        entry = _store["codes"].get(code)
        now = _now_iso()

        if not entry:
            return JSONResponse({"error": "invalid_grant", "error_description": "Unknown code"}, status_code=400)
        if entry.get("used"):
            return JSONResponse({"error": "invalid_grant", "error_description": "Code already used"}, status_code=400)
        if entry.get("expires_at", "") < now:
            return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"}, status_code=400)
        if entry.get("redirect_uri") != redirect_uri:
            return JSONResponse({"error": "invalid_grant", "error_description": "redirect_uri mismatch"}, status_code=400)
        if not _pkce_verify(code_verifier, entry.get("code_challenge", "")):
            return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

        entry["used"] = True
        access_token = secrets.token_urlsafe(48)
        refresh_token = secrets.token_urlsafe(48)
        ts = datetime.now(timezone.utc)
        _store["tokens"][access_token] = {"client_id": entry["client_id"], "expires_at": _iso(ts + TOKEN_TTL)}
        _store["refresh_tokens"][refresh_token] = {"client_id": entry["client_id"], "expires_at": _iso(ts + REFRESH_TTL)}
        _save()
        log.info("[oauth] issued access token for client %s", entry["client_id"])
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(TOKEN_TTL.total_seconds()),
            "refresh_token": refresh_token,
        })

    if grant_type == "refresh_token":
        rt = body.get("refresh_token", "")
        entry = _store["refresh_tokens"].get(rt)
        if not entry or entry.get("expires_at", "") < _now_iso():
            return JSONResponse({"error": "invalid_grant", "error_description": "Invalid or expired refresh token"}, status_code=400)
        access_token = secrets.token_urlsafe(48)
        _store["tokens"][access_token] = {"client_id": entry["client_id"], "expires_at": _iso(datetime.now(timezone.utc) + TOKEN_TTL)}
        _save()
        return JSONResponse({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(TOKEN_TTL.total_seconds()),
            "refresh_token": rt,
        })

    return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
