# Implementation Plan: Multi-user cortex server (v2.6.0, branch feat/multiuser)

## Context
Admin invites friends via link; each user sees only granted workspaces; each shared workspace has its own wiki repo as notes; GitHub tokens live encrypted in cortex.

## Changes
- **NEW `server/mcp/users.py`**: `/app/data/users.json` = users `{is_admin, workspaces[], active_ws, pw_hash (hashlib.scrypt), gh_token_enc (Fernet)}` + invites `{sha256(token): {username, workspaces, expires_at 7d, single-use}}`. Fns: `bootstrap_admin()` (user `admin` from `ADMIN_PASSWORD`, token from env `GITHUB_TOKEN`), `create_invite`, `accept_invite`, `check_password`, `grant/revoke`, `remove_user` (also kills its OAuth tokens), `can_access(user, ws)`, `set/get_github_token`. Workspaces registry `{name: {wiki_repo, owner}}` in same file.
- **`oauth.py:338 authorize_post`**: form gets username field (`_FORM_TEMPLATE`); check via `users.check_password`. Codes/tokens/refresh store `username` (`:362`, `:430`, `:447`). `verify_token` → `token_user(token) -> str|None`; legacy tokens without username = `admin` (no re-login).
- **`middleware.py:27`**: resolve user, put in `scope["state"]["user"]`, set contextvars; add `/invite/` prefix to unprotected. No-auth mode (no `ADMIN_PASSWORD`) = everyone admin, as today.
- **`state.py:21-31`**: contextvars `current_user`, `current_ws`; `get_active_workspace()` reads ctx, falls back to global; `set_active_workspace` persists per-user `active_ws`.
- **`tools.py`**: `class CortexMCP(MCPServer)` overriding `call_tool` (SDK `mcpserver/server.py:498`): user from `context.request_context.request.scope["state"]` (POST request, attached at `mcp/server/sse.py:257`), set contextvars, reject `ADMIN_TOOLS` for non-admins. Needed because SSE tools run outside the POST request task.
- **`tools_admin.py:179/206`**: `switch_workspace` checks `can_access` and allows registered-but-unindexed ws; `list_workspaces` filtered. New admin tools: `create_workspace(name, wiki_repo="")`, `invite_user(username, workspaces)` → link, `grant_workspace`, `revoke_workspace`, `list_users`, `remove_user`. Tokens never via MCP (would land in transcripts).
- **`repos.py:21`**: default ws = `get_active_workspace()` (fixes routes/reindex always hitting `default`); store `added_by` per repo.
- **`reindex.py:29,80,126,147`**: job carries `workspace`; worker sets ctx before `_run_reindex`. `_workspace_env(ws)` adds `GITHUB_TOKENS` json `{repo: token of added_by, fallback env}` and, for non-default ws, `NOTES_PATH=<data>/<ws>/wiki` after `_sync_wiki(ws)` git clone/pull. Non-default ws without `wiki_repo` → notes step skipped (vault-leak guard).
- **`indexer/index_code.py:29,91`**: per-repo token from `GITHUB_TOKENS`; auth via `git -c http.extraheader=...` instead of token in URL (stops PATs persisting in `.git/config`); strip token from existing remotes once.
- **`routes.py:55 webhook`**: fan out: code job per ws listing the repo, notes job per ws whose `wiki_repo` matches. All `/api/*`: ws from `?ws=`, checked by `can_access`. Admin-only: `/api/logs`, clear-cache all, user/invite APIs. `_api_github_repos:176` uses current user's token. New: `GET/POST /invite/{token}` (set password), `/api/users`, `/api/invites`, `/api/workspaces`, `POST /api/me/github-token`.
- **`template.py`**: workspace picker, admin Users panel (invite, grant/revoke, remove), "My GitHub token" field. Invite page template in `oauth.py` style.
- **`config.py`** `CORTEX_SECRET_KEY`; **`requirements.txt`** `cryptography`; **`docker-compose.yml`** env `CORTEX_SECRET_KEY=${CORTEX_SECRET_KEY:-}`.
- **Tests** `server/mcp/tests/test_users.py`, `test_access.py`: invite single-use/expiry, scrypt, Fernet roundtrip, grant/revoke, non-admin tool rejection, ws isolation across two users, notes-skip guard, legacy token → admin.

## Implementation Sequence
1. `users.py` + tests  2. `oauth.py` + `middleware.py`  3. `state.py` + `tools.py` override  4. `repos.py` + `reindex.py` + `index_code.py`  5. `tools_admin.py`  6. `routes.py` + invite page  7. `template.py` UI  8. config/compose/VERSION 2.6.0, docs.

## Edge Cases & Risks
- Deploy without `CORTEX_SECRET_KEY`: token storage refuses with clear error; env fallback keeps default ws working.
- Lost key: stored PATs unreadable, users re-enter; never logged.
- Same repo name, different owners (`alice/api` vs `bob/api`) collide in `REPOS_DIR` + payload `repo`: out of scope, documented.
- One shared reindex queue: friends wait in line; acceptable at this scale.
- Stats/search log stay global, tagged with username; admin-only view.

## Verification
`./run_tests.sh` then, on a branch image: admin invites `test` to ws `demo` → accept link → `test` sees only `demo`, cannot `switch_workspace("default")`, `search_notes` never returns vault files.
