# cortex

Personal RAG stack — Obsidian notes + source code indexed into Qdrant, exposed as MCP SSE server for Claude Code.

## Stack

- Python 3.12 + FastMCP (MCP Python SDK)
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

Auth: built-in OAuth 2.0 (Bearer token). Login at `/oauth/authorize` with `ADMIN_PASSWORD`.

**Features:**
- Search tab: query notes/code, toggle collections
- Admin tab: trigger reindex, view status, collection stats

**API endpoints (Bearer token required):**
- `POST /api/search` — `{"query": "...", "collections": ["notes","code"], "limit": 10}`
- `GET /api/status` — reindex status
- `POST /api/reindex` — `{"notes": true, "code": true, "repo": ""}`
- `GET /api/stats` — collection counts + ollama status

**Unprotected endpoints:**
- `GET /health` — healthchecks
- `POST /webhook` — GitHub webhooks (HMAC auth)
- `/sse` — MCP SSE (OAuth (Bearer))

## Structure

```
core/                   # shared lib — used by both server/ and local/
  chunker.py            # tree-sitter semantic chunking + sliding-window fallback
  cache.py              # load_cache / save_cache helpers
  graph.py              # facade — re-exports from code_graph, notes_graph, global_graph
  code_graph.py         # import/call/inheritance edges, centrality, Louvain
  notes_graph.py        # Obsidian wikilink graph + PPR augmentation
  global_graph.py       # cross-repo edges from root config files
server/
  mcp/                  # SSE server (Docker, deployed to cortex.hyvitech.org)
    server.py           # startup only — threads, routes, middleware wiring, uvicorn
    config.py           # env vars, embed(), warmup()
    state.py            # global mutable state, stats lifecycle, graph cache
    repos.py            # repo registry persistence
    onboarding.py       # ONBOARDING_TEMPLATE + _merge_onboarding()
    reindex.py          # job queue, _run_reindex, _enqueue, _reindex_worker
    middleware.py       # _BearerTokenMiddleware, _NormalizeSSEPath
    watcher.py          # debounced watchdog for notes changes
    routes.py           # all HTTP route handlers + webhook helpers
    tools.py            # FastMCP instance + all @mcp.tool() + @mcp.prompt()
    web_ui.py           # API handlers — search, status, stats
    template.py         # embedded HTML/CSS/JS dashboard + LOGO_SVG
    oauth.py            # custom OAuth 2.0 AS (RFC 8414/7591/7636, PKCE S256)
    requirements.txt
    Dockerfile          # build context is repo root
  indexer/              # code/notes indexers for server mode
    index.py            # notes indexer — heading-chunked, tags, modified_at
    index_code.py       # code indexer — clone/pull, embed, upsert
local/                  # cortex PyPI package — pipx install, stdio MCP, no server needed
  pyproject.toml        # package metadata, entry point: cortex = cortex.cli:cli
  cortex/
    cli.py              # cortex index <path>, cortex serve, cortex pull-models, cortex stats
    mcp_server.py       # all 8 MCP tools, FastMCP stdio transport
    indexer.py          # embedded Qdrant indexer (notes + code)
    embedder.py         # fastembed dense (nomic-embed-text-v1.5) + BM25 sparse
    config.py           # ~/.cortex paths, VECTOR_SIZE, VERSION
    state.py            # graph cache, stats lifecycle
docker-compose.yml      # ollama + qdrant + cortex-mcp (server mode)
```

## MCP tools

- `search_notes(query, limit)` — semantic search over Obsidian notes + PPR wikilink augmentation
- `search_code(query, limit)` — semantic search over source code + centrality re-ranking
- `get_neighbors(file, repo)` — imports + imported-by for a file
- `get_community(repo, community_id)` — all files in a Louvain cluster
- `reindex(notes, code, repo)` — async, returns immediately
- `reindex_status()` — check progress of last reindex
- `get_stats(all?)` — efficiency metrics; `all=True` shows all persisted versions side-by-side
- `get_onboarding(existing_content?)` — returns setup instructions + preferences; pass existing CLAUDE.md content to merge

## MCP prompts

- `/onboarding` — full project setup: CLAUDE.md, git config, rtk, caveman skill, Cortex verification

## Key patterns

- 4-layer architecture (deps flow downward only):
  - **Foundation**: `config`, `oauth`, `template`, `onboarding` — no local deps
  - **Domain**: `state`, `repos` ← config
  - **Service**: `reindex` ← state, repos; exposes `_enqueue()`, `get_status()`, `get_queue_snapshot()` as public API
  - **Transport**: `routes` (HTTP), `tools` (MCP) ← service API only; `middleware`, `watcher` ← config/service
  - **Composition**: `server` ← everything
- `mcp.sse_app()` returns Starlette app — mounted at `/sse` in server.py
- `_job_queue` (deque) + `_reindex_worker` thread processes jobs sequentially — webhooks/watcher/MCP tool all call `_enqueue()`, nothing dropped
- `_enqueue()` coalesces same-repo incremental webhook jobs (merges file lists instead of queuing duplicate)
- Watchdog debounces 60s before triggering notes reindex (env: `WATCH_DEBOUNCE`)
- Code indexer clones repos via `GITHUB_TOKEN` env var — required for private repos
- Qdrant `query_points()` API (v1.17+) — `search()` is removed

## Env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `NOTES_PATH` | `/notes` | Notes mount path |
| `WATCH_DEBOUNCE` | `60` | Seconds to debounce watcher |
| `GITHUB_TOKEN` | — | For cloning private repos |
| `WEBHOOK_SECRET` | — | GitHub webhook signature secret |
| `ADMIN_PASSWORD` | — | OAuth login password (required if auth enabled) |
| `BASE_URL` | `http://localhost:8765` | Public URL for OAuth metadata |

## After changes

Push to main → CI builds new image. On LXC:
```bash
docker compose pull cortex-mcp && docker compose up -d cortex-mcp
```
