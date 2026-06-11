# cortex

Personal RAG stack — semantic search over Obsidian notes and source code, exposed as an MCP server for Claude Code.

Two modes:

| | **Local** | **Server** |
|---|---|---|
| Transport | stdio | SSE (HTTPS) |
| Embeddings | fastembed (local, no GPU) | Ollama (nomic-embed-text) |
| Vector store | embedded Qdrant (`~/.cortex`) | Qdrant container |
| Install | `pipx install` | Docker Compose |
| Auth | none | OAuth 2.0 |

---

## Local mode

No server, no Docker. Runs as a stdio MCP tool directly in Claude Code.

**Install:**
```bash
pipx install 'cortex @ git+https://github.com/Xoudusz/cortex#subdirectory=local'
cortex install
```

`cortex install` downloads the embedding models and registers the MCP server in Claude Code. Restart Claude Code after.

**Index your notes/code:**
```bash
cortex index ~/notes
cortex index ~/projects/my-app
```

**MCP tools available after setup:**

| Tool | Description |
|------|-------------|
| `search_notes(query, limit)` | Semantic search over notes + PPR wikilink augmentation |
| `search_code(query, limit)` | Semantic search over code + centrality re-ranking |
| `get_neighbors(file, repo)` | Imports and imported-by for a file |
| `get_community(repo, community_id)` | All files in a Louvain cluster |
| `reindex(path)` | Re-index a path (async) |
| `reindex_status()` | Check reindex progress |
| `get_stats()` | Efficiency metrics |
| `get_onboarding(existing_content)` | CLAUDE.md template with cortex instructions |

---

## Server mode

Full stack with web UI, GitHub webhooks, OAuth, and multi-repo code indexing.

**Services:**

| Service | Port | Description |
|---------|------|-------------|
| Ollama | 11434 | Embeddings via `nomic-embed-text` |
| Qdrant | 6333 | Vector store — collections: `notes`, `code` |
| cortex-mcp | 8765 | MCP SSE server + web UI |

**Deploy (Portainer):**

1. Stacks → Add Stack → Repository
2. URL: `https://github.com/Xoudusz/cortex`
3. Auth: `Xoudusz` / PAT (Contents: Read)
4. Compose path: `docker-compose.yml`
5. Set env vars: `ADMIN_PASSWORD`, `BASE_URL`, `GITHUB_TOKEN`, `WEBHOOK_SECRET`
6. Deploy

```bash
# Pull embedding model after first deploy
docker exec ollama ollama pull nomic-embed-text
```

**Register MCP in Claude Code:**
```bash
claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse
```

OAuth login opens in browser on first connection. Tokens persist (30-day access, 90-day refresh).

**Environment variables:**

| Var | Default | Purpose |
|-----|---------|---------|
| `ADMIN_PASSWORD` | — | Required — OAuth login password |
| `BASE_URL` | `https://cortex.hyvitech.org` | Public URL for OAuth metadata |
| `GITHUB_TOKEN` | — | For cloning private repos |
| `WEBHOOK_SECRET` | — | GitHub webhook HMAC validation |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `NOTES_PATH` | `/notes` | Notes mount (watched for changes) |
| `MCP_PORT` | `8765` | Server bind port |
| `WATCH_DEBOUNCE` | `60` | Seconds to debounce notes watcher |

**Endpoints:**

| Path | Method | Auth | Description |
|------|--------|------|-------------|
| `/` | GET | OAuth | Web UI dashboard |
| `/sse` | GET | OAuth | MCP SSE endpoint |
| `/health` | GET | None | Health check |
| `/webhook` | POST | HMAC | GitHub push → code reindex |
| `/api/graph/{repo}` | GET | OAuth | Graph JSON |
| `/api/stats` | GET | OAuth | Efficiency metrics |
| `/authorize` | GET/POST | None | OAuth login |
| `/token` | POST | None | OAuth token exchange |
| `/.well-known/oauth-authorization-server` | GET | None | OAuth AS metadata |

**Re-index:**
```
reindex()                               # all
reindex(code=False)                     # notes only
reindex(notes=False, repo="arr-client") # single repo
```

Auto-triggers: notes watcher (debounced 60s), GitHub webhook on push.

**After image changes:**
```bash
docker compose pull cortex-mcp && docker compose up -d cortex-mcp
```

---

## Repository structure

```
core/          # shared lib — chunker, cache, graph (used by server/ and local/)
server/
  mcp/         # SSE server source + Dockerfile
  indexer/     # notes + code indexers for server mode
local/         # cortex PyPI package (local/stdio mode)
  pyproject.toml
  cortex/      # cli.py, mcp_server.py, indexer.py, embedder.py
docker-compose.yml
```

---

## Graph layer

Graph-augmented RAG builds structural graphs at index time, then uses them to boost retrieval.

### Code graph

Built from AST edges (no LLM):

- **Import edges** — `import`/`from` (Python), `import`/`require` (JS/TS), `use` (Rust). Resolves path aliases (`$lib/` → `src/lib/`).
- **Call edges** — named imports matched against call sites
- **Inheritance edges** — `class Foo(Bar)` (Python), `extends`/`implements` (TS/Kotlin)
- **Degree centrality** — files imported by many others score higher (`score * (1 + 0.2 * centrality)`)
- **Louvain communities** — files clustered by connectivity

### Notes graph

Built from `[[wikilink]]` patterns. **Personalized PageRank (PPR)** walks from vector-matched notes at query time, surfacing related notes that are structurally connected but semantically distant.

---

## Auth (server mode)

Built-in OAuth 2.0 AS (`server/mcp/oauth.py`) — no external provider needed.

- **Standards:** RFC 8414, RFC 7591 (Dynamic Client Registration), RFC 7636 (PKCE S256)
- **Grants:** Authorization code + refresh token
- **Tokens:** 30-day access, 90-day refresh
- **Persistence:** `/app/data/oauth_state.json` — survives restarts

---

## Volume paths (server mode)

| Host path | Container path | Purpose |
|-----------|----------------|---------|
| `/mnt/data/ai/ollama` | `/root/.ollama` | Ollama models (RAID) |
| `/home/docker/volumes/qdrant/storage` | `/qdrant/storage` | Qdrant data |
| `/home/docker/volumes/syncthing/notes` | `/notes` | Notes (read-only, Syncthing) |
| `/home/docker/volumes/cortex/config` | `/app/data` | Graphs, repos config, OAuth state |
