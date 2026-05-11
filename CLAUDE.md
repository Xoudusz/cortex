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

Auth handled by Authelia at NPM proxy level. No in-app auth required.

**Features:**
- Search tab: query notes/code, toggle collections
- Admin tab: trigger reindex, view status, collection stats

**API endpoints (Authelia-protected):**
- `POST /api/search` — `{"query": "...", "collections": ["notes","code"], "limit": 10}`
- `GET /api/status` — reindex status
- `POST /api/reindex` — `{"notes": true, "code": true, "repo": ""}`
- `GET /api/stats` — collection counts + ollama status

**Unprotected endpoints:**
- `GET /health` — healthchecks
- `POST /webhook` — GitHub webhooks (HMAC auth)
- `/sse` — MCP SSE (X-API-Key header)

## Structure

```
mcp/
  server.py         # FastMCP SSE server — all tools + webhook + watcher
  web_ui.py         # Web dashboard HTML + API routes
  requirements.txt
  Dockerfile        # build context is repo root (copies indexer/ scripts in)
indexer/
  index.py          # Notes indexer — heading-chunked, tags, modified_at
  index_code.py     # Code indexer — 30-line sliding window, github_url
docker-compose.yml  # ollama + qdrant + cortex-mcp
```

## MCP tools

- `search_notes(query, limit)` — semantic search over Obsidian notes
- `search_code(query, limit)` — semantic search over source code
- `reindex(notes, code, repo)` — async, returns immediately
- `reindex_status()` — check progress of last reindex
- `get_onboarding(existing_content?)` — returns setup instructions + preferences; pass existing CLAUDE.md content to merge

## MCP prompts

- `/onboarding` — full project setup: CLAUDE.md, git config, rtk, caveman skill, Cortex verification

## Key patterns

- `mcp.sse_app()` returns Starlette app — mounted with `/webhook` route for GitHub push events
- `_reindex_lock` prevents concurrent reindexes
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

## After changes

Push to main → CI builds new image. On LXC:
```bash
docker compose pull cortex-mcp && docker compose up -d cortex-mcp
```
