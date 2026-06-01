# cortex

Personal RAG stack — Obsidian notes + source code indexed into Qdrant, exposed as an MCP SSE server for Claude Code.

## Services

| Service | Port | Description |
|---------|------|-------------|
| Ollama | 11434 | Embeddings via `nomic-embed-text` |
| Qdrant | 6333 | Vector store — collections: `notes`, `code` |
| cortex-mcp | 8765 | MCP SSE server for Claude Code |

## Endpoints

| Path | Method | Auth | Description |
|------|--------|------|-------------|
| `/` | GET | OAuth (Bearer) | Web UI dashboard |
| `/sse` | GET | OAuth (Bearer) | MCP SSE endpoint (rewritten to `/sse/sse` via ASGI middleware) |
| `/health` | GET | None | Health check for autoheal |
| `/webhook` | POST | HMAC signature | GitHub push webhook — triggers per-repo code reindex |
| `/api/graph/{repo}` | GET | OAuth (Bearer) | Graph JSON — `notes` = wikilink, `global` = cross-repo, or repo name |
| `/api/stats` | GET | OAuth (Bearer) | Efficiency metrics — centrality lift, PPR hit rate, cache stats |
| `/authorize` | GET/POST | None | OAuth authorization endpoint — password-gated login form |
| `/token` | POST | None | OAuth token endpoint — code exchange + refresh |
| `/register` | POST | None | OAuth Dynamic Client Registration (RFC 7591) |
| `/.well-known/oauth-authorization-server` | GET | None | OAuth AS metadata (RFC 8414) |
| `/.well-known/oauth-protected-resource` | GET | None | OAuth protected resource metadata |

## Deploy (Portainer)

1. Stacks → Add Stack → Repository
2. URL: `https://github.com/Xoudusz/cortex`
3. Auth: `Xoudusz` / PAT (Contents: Read)
4. Compose path: `docker-compose.yml`
5. Set env vars in Portainer stack settings: `ADMIN_PASSWORD`, `BASE_URL`, `GITHUB_TOKEN`, `WEBHOOK_SECRET`
6. Deploy

**Post-deploy — pull embedding model:**
```bash
docker exec ollama ollama pull nomic-embed-text
```

**Post-deploy — index everything** (via Claude Code after MCP is registered):
```
reindex()
```
Or set `GITHUB_TOKEN` env var in Portainer stack settings to enable private repo cloning.

## Register MCP in Claude Code (run on client)

```bash
claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse
```

OAuth login opens in browser on first connection. Tokens persist (30-day access, 90-day refresh).

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `ADMIN_PASSWORD` | — | Required — OAuth login form password |
| `BASE_URL` | `https://cortex.hyvitech.org` | Public URL — used in OAuth metadata + token issuer |
| `GITHUB_TOKEN` | — | For cloning private repos |
| `WEBHOOK_SECRET` | — | GitHub webhook HMAC signature validation |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `NOTES_PATH` | `/notes` | Notes mount path (watched for changes) |
| `MCP_HOST` | `0.0.0.0` | Server bind host |
| `MCP_PORT` | `8765` | Server bind port |
| `WATCH_DEBOUNCE` | `60` | Seconds to debounce notes watcher |

## Re-index

**Manual** (via Claude Code MCP):
```
reindex()           # all
reindex(code=False) # notes only
reindex(notes=False, repo="svelte-radio")  # single repo
```

**Automatic triggers:**
- **Notes watcher** — detects .md changes, debounces 60s, triggers notes reindex
- **GitHub webhook** — on push event, triggers code reindex for that repo only

**CLI fallback:**
```bash
docker compose --profile index run --rm cortex-indexer
```

## Qdrant collections

| Collection | Chunk strategy | Key payload fields |
|------------|---------------|-------------------|
| `notes` | H1-H3 heading boundaries | `file`, `heading`, `tags`, `modified_at`, `text` |
| `code` | Tree-sitter semantic (functions/classes) with sliding-window fallback | `repo`, `file`, `language`, `start_line`, `end_line`, `github_url`, `text`, `centrality`, `community_id`, `imports`, `imported_by` |

Tree-sitter languages: Python, JavaScript, TypeScript, Kotlin. Others fallback to 30-line sliding window.

## Graph Layer

Graph-augmented RAG builds a structural graph alongside vector embeddings, then uses it to boost retrieval quality.

### Code graph (`/app/data/graph_{repo}.json`)

Built at index time from AST edges (no LLM needed):

- **Import edges** — `import`/`from` (Python), `import`/`require` (JS/TS), `use` (Rust)
- **Call edges** — JS/TS named imports matched against call sites → edge to source file
- **Inheritance edges** — `class Foo(Bar)` (Python), `extends`/`implements` (TS/Kotlin)
- Edge priority: `inherits > call > import`; tagged in graph JSON + D3 visualization (distinct arrow colors)
- **Degree centrality** — files imported by many others score higher in search results (`final_score = vector_score * (1 + 0.2 * centrality)`)
- **Louvain communities** — files clustered by connectivity; `community_id` groups related modules

### Notes graph (`/app/data/graph_notes.json`)

Built from `[[wikilink]]` patterns in Markdown files:

- **Personalized PageRank (PPR)** — query-time walk seeded from vector-matched notes; surfaces related notes that are structurally connected but semantically distant from the query string

### MCP tools

| Tool | Description |
|------|-------------|
| `search_code` | Vector search + centrality re-ranking; results include `centrality` and `community_id` |
| `search_notes` | Vector search + PPR augmentation; PPR-surfaced notes tagged `[via wikilinks]` |
| `get_neighbors(file, repo)` | Returns direct imports and imported-by list for a file |
| `get_community(repo, community_id)` | Lists all files in a Louvain cluster; high-centrality files starred |

### Efficiency metrics (`/api/stats`)

Tracks in-memory counters (resets on container restart):

| Metric | Description |
|--------|-------------|
| `search_code_calls` | Total `search_code` invocations |
| `centrality_lift_total` | Sum of score boost from centrality across all results |
| `centrality_lift_count` | Results where centrality > 0 (graph coverage) |
| `search_notes_calls` | Total `search_notes` invocations |
| `ppr_fires` | Times PPR returned ≥1 extra result |
| `ppr_results_added` | Total extra results surfaced by PPR |
| `graph_cache_hits` / `graph_cache_misses` | Graph JSON load efficiency |

Stats card displayed in Admin tab of web UI dashboard.

### Cross-repo graph (`/app/data/graph_global.json`)

Built at full reindex time (no `--repo` flag). Scans root config files (`package.json`, `requirements.txt`, `go.mod`, `docker-compose.yml`, `.env*`) for mentions of other indexed repos and builds directed repo-level edges.

Exposed as `GET /api/graph/global`. Dashboard: Graph tab → **★ Global (cross-repo)** → force-directed view with repo nodes and dashed cross-repo edges. Click node shows which files create each reference.

### Dashboard — Graph tab

- **Per-repo view:** force-directed D3.js graph — nodes sized by centrality, colored by community, arrows colored by edge type (import/call/inherits)
- **★ Global view:** repo nodes with dashed cross-repo edges; click shows source files

## Auth

Cortex is its own OAuth 2.0 Authorization Server (`mcp/oauth.py`) — no external identity provider needed.

- **Standards:** RFC 8414 (AS metadata), RFC 7591 (Dynamic Client Registration), RFC 7636 (PKCE S256)
- **Grants:** Authorization code + refresh token
- **Session:** 30-day access tokens, 90-day refresh tokens
- **Persistence:** OAuth state saved to `/app/data/oauth_state.json` — survives container restarts
- **Gate:** Password prompt at `/authorize` (set via `ADMIN_PASSWORD`)

Claude Desktop and Claude Code discover the OAuth server automatically via `/.well-known/oauth-authorization-server`.

## Volume paths

- Ollama models: `/mnt/data/ai/ollama` (RAID)
- Qdrant storage: `/home/docker/volumes/qdrant/storage`
- Notes (read-only mount from Syncthing): `/home/docker/volumes/syncthing/notes`
- App data (graphs, repos config, OAuth state): `/home/docker/volumes/cortex/config` → `/app/data/`
