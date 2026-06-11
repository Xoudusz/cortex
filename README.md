# cortex

Semantic search over your code and notes, as an MCP server for Claude Code.

Index your repos and Obsidian vault once. Search from any coding session — Claude finds relevant files, functions, and notes without you having to remember where anything is.

**Two modes:**

| | **Local** | **Server** |
|---|---|---|
| Transport | stdio | SSE (HTTPS) |
| Embeddings | fastembed (CPU, no GPU) | Ollama (nomic-embed-text) |
| Vector store | embedded Qdrant (`~/.cortex`) | Qdrant container |
| Install | `pipx install cortex-local` | Docker Compose |
| Auth | none | OAuth 2.0 |

---

## Quick start (local mode)

No server, no Docker. Runs as a stdio MCP tool directly in Claude Code.

**Recommended — via Claude Code plugin (auto-registers MCP):**

```bash
# 1. Register cortex marketplace (one-time)
claude plugin marketplace add cortex https://github.com/Xoudusz/cortex.git

# 2. Install the plugin
claude plugin install cortex@cortex

# 3. Install the cortex binary
pipx install cortex-local
```

Restart Claude Code. The session-start hook pulls embedding models and registers the MCP automatically.

**Legacy CPU (no SSE4.2)?** Use the `[legacy]` extra with Python 3.12 before step 3:
```bash
pipx install "cortex-local[legacy]" --python python3.12
```

**Without the plugin (manual):**

```bash
pipx install cortex-local
cortex install   # pulls models + registers MCP
# restart Claude Code
```

Then index your projects:

```bash
cortex index ~/notes
cortex index ~/projects/my-app
```

---

## MCP tools

| Tool | Description |
|------|-------------|
| `search_code(query, limit)` | Semantic code search + centrality re-ranking |
| `search_notes(query, limit)` | Semantic notes search + PPR wikilink augmentation |
| `get_neighbors(file, repo)` | Imports and imported-by for a file |
| `get_community(repo, community_id)` | All files in the same Louvain cluster |
| `reindex(notes, code, repo)` | Async re-index (returns immediately) |
| `reindex_status()` | Check reindex progress |
| `get_stats()` | Efficiency metrics |
| `get_onboarding(existing_content)` | CLAUDE.md template with cortex instructions |

---

## Server mode

Full stack with web dashboard, GitHub webhooks, OAuth, and multi-repo indexing. Good for self-hosting on a home server or VM shared across machines.

**Services:**

| Service | Port | Description |
|---------|------|-------------|
| Ollama | 11434 | Embeddings via `nomic-embed-text` |
| Qdrant | 6333 | Vector store — collections: `notes`, `code` |
| cortex-mcp | 8765 | MCP SSE server + web dashboard |

**Deploy:**

```bash
git clone https://github.com/Xoudusz/cortex
cd cortex
cp .env.example .env   # edit ADMIN_PASSWORD and BASE_URL at minimum
docker compose up -d

# Pull embedding model on first run
docker exec ollama ollama pull nomic-embed-text
```

**Register MCP in Claude Code:**
```bash
claude mcp add cortex -s user --transport sse https://your-server:8765/sse
```

OAuth login opens in browser on first connection. Tokens persist (30-day access, 90-day refresh).

**Environment variables:**

| Var | Default | Purpose |
|-----|---------|---------|
| `ADMIN_PASSWORD` | — | Required — OAuth login password |
| `BASE_URL` | `http://localhost:8765` | Public URL for OAuth metadata |
| `GITHUB_TOKEN` | — | For cloning private repos |
| `WEBHOOK_SECRET` | — | GitHub webhook HMAC validation |
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `NOTES_PATH` | `/notes` | Notes mount (watched for changes) |
| `MCP_PORT` | `8765` | Server bind port |
| `WATCH_DEBOUNCE` | `60` | Seconds to debounce notes watcher |

**After image updates:**
```bash
docker compose pull cortex-mcp && docker compose up -d cortex-mcp
```

---

## Graph layer

Graph-augmented RAG builds structural graphs at index time, then uses them to boost retrieval.

### Code graph

Built from static analysis (no LLM):

- **Import edges** — `import`/`from` (Python), `import`/`require` (JS/TS/Svelte), `import` (Kotlin). Resolves path aliases (`$lib/` → `src/lib/`).
- **Call edges** — named imports matched against call sites
- **Inheritance edges** — `class Foo(Bar)` (Python), `extends`/`implements` (TS/Kotlin)
- **Degree centrality** — files imported by many others score higher in search results
- **Louvain communities** — files clustered by structural connectivity

### Notes graph

Built from `[[wikilink]]` patterns. **Personalized PageRank (PPR)** walks from vector-matched notes at query time, surfacing structurally connected notes that would otherwise be missed.

---

## Repository structure

```
core/          # shared lib — chunker, cache, graph (used by server/ and local/)
server/
  mcp/         # SSE server + web dashboard + Dockerfile
  indexer/     # notes + code indexers for server mode
local/         # PyPI package (cortex-local) — stdio MCP, no server needed
  pyproject.toml
  cortex/      # cli.py, mcp_server.py, indexer.py, embedder.py
.claude-plugin/ # Claude Code plugin manifest
hooks/         # session-start hook for plugin
skills/        # cortex-search, cortex-index, cortex-setup skill guides
docker-compose.yml
```

---

## Auth (server mode)

Built-in OAuth 2.0 AS — no external provider needed.

- RFC 8414 (AS metadata), RFC 7591 (Dynamic Client Registration), RFC 7636 (PKCE S256)
- Authorization code + refresh token flow
- 30-day access tokens, 90-day refresh tokens
- State persists in `/app/data/oauth_state.json` across restarts
