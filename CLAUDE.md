# cortex

Personal RAG stack — Obsidian notes + source code indexed into Qdrant, exposed as MCP SSE server for Claude Code.

## Stack

- Python 3.12 + MCP SDK v2 (MCPServer from `mcp.server.mcpserver`)
- Qdrant (vector store) + Ollama (nomic-embed-text embeddings)
- watchdog for auto-reindex on notes change
- Docker Compose — deployed on portainer LXC (192.168.68.103)
- CI: push to main → GHCR image build → `ghcr.io/xoudusz/cortex-mcp:latest`

## Web UI

Dashboard at `/` for search and admin operations.

**Access:**
```
https://cortex.hyvitech.org/
```

Auth: built-in OAuth 2.0 (Bearer token). Login at `/oauth/authorize` with username + password: `admin` (or blank) uses `ADMIN_PASSWORD`; members are created via single-use invite links (`/invite/{token}`). Members only get MCP + `/api/me`; every other `/api/*` is admin-only.

**Features:**
- Search tab: query notes/code, toggle collections
- Admin tab: trigger reindex, view status, collection stats

**API endpoints (Bearer token required):**
- `POST /api/search` — `{"query": "...", "collections": ["notes","code"], "limit": 10}`
- `GET /api/status` — reindex status
- `POST /api/reindex` — `{"notes": true, "code": true, "repo": ""}`
- `GET /api/stats` — collection counts + ollama status
- `GET|PUT|DELETE /api/settings` — GitHub token status / set (validated against GitHub, stored in `data/settings.json` 0600, overrides env) / clear. Never returns the token
- `GET /api/github/repos` — owner + collaborator + org repos, paginated

**Unprotected endpoints:**
- `GET /health` — healthchecks
- `POST /webhook` — GitHub webhooks (HMAC auth)
- `/sse` — MCP SSE (OAuth (Bearer))

## Structure

```
core/                   # ONE shared lib — bundled into the wheel as cortex/core by local/hatch_build.py
  chunker.py            # tree-sitter + Roslyn chunking + Razor @code extraction + sliding-window
  godot.py              # GDScript spans, .tscn/.tres/project.godot summaries, Godot graph edges (res:// + uid://)
  cache.py              # load_cache / save_cache — {mtime, hash} format, backward-compat
  graph.py              # facade — re-exports from code_graph, notes_graph, global_graph
  code_graph.py         # import/call/inheritance edges, centrality, Louvain + inject_roslyn_edges()
  notes_graph.py        # Obsidian wikilink graph + PPR augmentation
  global_graph.py       # cross-repo edges from root config files
  roslyn_analyzer.py    # subprocess wrapper for CortexAnalyzer binary
  roslyn_tool/          # .NET 8 console app — CSharpSyntaxTree.ParseText, no MSBuild needed
server/
  mcp/                  # SSE server (Docker, deployed to cortex.hyvitech.org)
    server.py           # startup only — threads, routes, middleware wiring, uvicorn
    config.py           # env vars, embed(), warmup()
    state.py            # global mutable state, stats lifecycle, graph cache, per-request user/workspace contextvars
    users.py            # users.json (0600): users (scrypt), invites (sha256, 7d, single use), shared-workspace registry
    repos.py            # repo registry persistence
    onboarding.py       # ONBOARDING_TEMPLATE + _merge_onboarding()
    reindex.py          # job queue, _run_reindex, _enqueue, _reindex_worker
    middleware.py       # _BearerTokenMiddleware, _NormalizeSSEPath
    watcher.py          # debounced watchdog for notes changes
    routes.py           # all HTTP route handlers + webhook helpers
    tools.py            # CortexMCP (binds caller in call_tool, ADMIN_TOOLS gate) + tool registration
    tools_users.py      # whoami + admin tools: workspaces, repos, invites, users
    web_ui.py           # API handlers — search, status, stats
    template.py         # embedded HTML/CSS/JS dashboard + LOGO_SVG
    oauth.py            # custom OAuth 2.0 AS (RFC 8414/7591/7636, PKCE S256)
    requirements.txt
    Dockerfile          # multi-stage: dotnet/sdk:8.0-bookworm-slim builds CortexAnalyzer → python:3.12-slim
  indexer/              # code/notes indexers for server mode
    index.py            # notes indexer — heading-chunked, tags, modified_at
    index_code.py       # code indexer — clone/pull, embed, upsert
local/                  # cortex PyPI package — pipx install, stdio MCP, no server needed
  pyproject.toml        # package metadata, entry point: cortex = cortex.cli:cli
  cortex/
    cli.py              # cortex index/serve/stats/search-log/workspace commands
    mcp_server.py       # 12 MCP tools, FastMCP stdio transport
    indexer.py          # embedded Qdrant indexer (notes + code), tqdm progress
    embedder.py         # fastembed dense (nomic-embed-text-v1.5) + BM25 sparse
    config.py           # ~/.cortex paths, config.toml (get_config, save_last_indexed_path)
    state.py            # graph cache, stats lifecycle
    watcher.py          # CortexWatcher — all index roots, code + .md, write events only, debounced
    db.py               # shared embedded-Qdrant client per workspace + index_lock (never open QdrantClient elsewhere)
    __init__.py         # source checkouts: exposes <repo>/core as cortex.core (no symlink — broke Windows)
  hatch_build.py        # build hook: force-includes ../core as cortex/core when present
  tests/test_stdio_init.py  # e2e: `cortex serve` answers MCP initialize (CI: Linux test job; no Windows runner)
docker-compose.yml      # ollama + qdrant + cortex-mcp (server mode)
```

## MCP tools

- `search_notes(query, limit)` — semantic search over Obsidian notes + PPR wikilink augmentation
- `search_code(query, limit)` — semantic search over source code + centrality re-ranking
- `search_all(query, limit)` — search both collections simultaneously, combined output
- `get_neighbors(file, repo)` — imports + imported-by for a file
- `get_community(repo, community_id)` — all files in a Louvain cluster
- `reindex(notes, code, repo, force?)` — async; `force=True` clears embed cache first (~10x slower)
- `reindex_status()` — check progress of last reindex
- `clear_cache(all_workspaces?)` — delete embed cache for current workspace (or all); not auto-approved
- `get_stats(all?)` — efficiency metrics; `all=True` shows all persisted versions side-by-side
- `get_onboarding(existing_content?, force?)` — returns setup instructions + preferences; pass existing CLAUDE.md content to merge; `force=True` replaces stale Cortex section
- `switch_workspace(name)` — switch active workspace (isolated Qdrant collections + repos)
- `list_workspaces()` — list the caller's workspaces and their index status
- `whoami()` — caller, role, active workspace
- admin only (`tools.ADMIN_TOOLS`): `clear_cache`, `get_stats`, `create_workspace(name, wiki_repo?)`, `delete_workspace`, `set_workspace_wiki`, `add_repo(repo, workspace)`, `remove_repo`, `invite_user(username, workspaces)`, `list_users`, `remove_user`, `grant_workspace`, `revoke_workspace`

## MCP prompts

- `/onboarding` — full project setup: CLAUDE.md, git config, rtk, caveman skill, Cortex verification

## Key patterns

- 4-layer architecture (deps flow downward only):
  - **Foundation**: `config`, `users`, `oauth` (← users), `template`, `onboarding` — no other local deps
  - **Domain**: `state`, `repos` ← config
  - **Service**: `reindex` ← state, repos; exposes `_enqueue()`, `get_status()`, `get_queue_snapshot()` as public API
  - **Transport**: `routes` (HTTP), `tools` (MCP) ← service API only; `middleware`, `watcher` ← config/service
  - **Composition**: `server` ← everything
- `mcp.sse_app()` returns Starlette app — mounted at `/sse` in server.py
- `_job_queue` (deque) + `_reindex_worker` thread processes jobs sequentially — webhooks/watcher/MCP tool all call `_enqueue()`, nothing dropped
- `_enqueue()` coalesces same-repo incremental webhook jobs (merges file lists instead of queuing duplicate)
- Watchdog debounces 60s before triggering notes reindex (env: `WATCH_DEBOUNCE`)
- Code indexer clones repos with `config.get_github_token()` (dashboard setting > `GITHUB_TOKEN` env), passed to the subprocess env by `reindex._workspace_env()`
- Multi-user: never read `_active_workspace` directly — use `state.get_active_workspace()` (per-user via contextvars). Binding happens in `_BearerTokenMiddleware` (HTTP; admin `/api/*` always binds `default`), `CortexMCP.call_tool` (MCP — SSE tools run outside the POST task, so the middleware binding never reaches them), and `_reindex_worker` (each job carries `ws`). A bound user with no workspace raises `PermissionError` instead of falling back to `default`
- `default` = admin's private workspace (vault + own repos), never grantable. Shared workspaces are code repos + optional wiki repo: notes reindex there clones the wiki (`reindex._sync_wiki`, auth via `http.extraheader`, not URL) and never reads `NOTES_PATH`
- Webhook fans out: code job per workspace tracking the repo, notes job per workspace whose `wiki_repo` matches
- Per-repo excludes: `core.chunker.repo_ignore_patterns()` (`.cortexignore` + `.gdignore` dirs); full reindex deletes chunks of gone/excluded files
- Qdrant `query_points()` API (v1.17+) — `search()` is removed

## Env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `NOTES_PATH` | `/notes` | Notes mount path |
| `WATCH_DEBOUNCE` | `60` | Seconds to debounce watcher |
| `EXCLUDE_PATTERNS` | — | Comma-separated glob patterns to skip (e.g. `*.log,tmp/*`) |
| `GITHUB_TOKEN` | — | For cloning private repos |
| `WEBHOOK_SECRET` | — | GitHub webhook signature secret |
| `ADMIN_PASSWORD` | — | OAuth login password (required if auth enabled) |
| `BASE_URL` | `http://localhost:8765` | Public URL for OAuth metadata |

## Local mode config (~/.cortex/config.toml)

```toml
[watch]
enabled = true          # auto-start watcher on cortex serve
debounce_seconds = 2.0

[index]
last_path = ""          # auto-set by cortex index <path> (POSIX form)
exclude_patterns = []   # glob patterns, e.g. ["*.log", "tmp/*"]
```

Per workspace `~/.cortex/workspaces/<ws>/index_meta.json`: `schema` (bump `INDEX_SCHEMA` in config.py on incompatible payload changes — old index is wiped) + `roots` {path: indexed_at, git_head, notes, code}. Local stdio server must never print to stdout (JSON-RPC channel) — use logging.

## Eval

```bash
cd /root/projects/cortex
python3 eval/run.py                                                        # hit@k + MRR against golden set
python3 eval/run.py --save baseline                                        # save named baseline
python3 eval/run.py --compare baseline                                     # diff against saved baseline
python3 eval/run.py --url https://cortex.hyvitech.org/api --token <tok>   # via HTTP API
```

Golden set: `eval/golden.json` (21 queries). Baselines: `eval/baselines.json`.
Requires reindex before meaningful results. Qdrant: `http://192.168.68.103:6333`.

## After changes

Push to main → CI builds new image. On LXC:
```bash
docker compose pull cortex-mcp && docker compose up -d cortex-mcp
```

## Issue workflow

To auto-close a GitHub issue on merge, put `Closes #N` in the **PR body** (not commit message). Direct pushes to main do not trigger keyword auto-close. Always use a PR when a commit resolves an issue. Token lacks `issues: write` so manual close via UI is the fallback.
