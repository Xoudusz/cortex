# cortex

Personal RAG stack — Obsidian notes + source code indexed into Qdrant, exposed as an MCP SSE server for Claude Code.

## Services

| Service | Port | Description |
|---------|------|-------------|
| Ollama | 11434 | Embeddings via `nomic-embed-text` |
| Qdrant | 6333 | Vector store — collections: `notes`, `code` |
| cortex-mcp | 8765 | MCP SSE server for Claude Code |

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/` | GET | Web UI (Authelia protected) |
| `/sse` | GET | MCP SSE endpoint (requires `x-api-key` header; internally rewritten to `/sse/sse` via ASGI middleware) |
| `/health` | GET | Health check for autoheal |
| `/webhook` | POST | GitHub push webhook — triggers per-repo code reindex |
| `/api/graph/{repo}` | GET | Graph JSON for repo (`notes` for wikilink graph, or repo name for code graph) |

## Deploy (Portainer)

1. Stacks → Add Stack → Repository
2. URL: `https://github.com/Xoudusz/cortex`
3. Auth: `Xoudusz` / PAT (Contents: Read)
4. Compose path: `docker-compose.yml`
5. Set `API_KEY` env var in Portainer stack settings
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
claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse \
  --header "x-api-key: <your-api-key>"
```

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------| 
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `NOTES_PATH` | `/notes` | Notes mount path (watched for changes) |
| `MCP_HOST` | `0.0.0.0` | Server bind host |
| `MCP_PORT` | `8765` | Server bind port |
| `API_KEY` | — | Required for `/sse` endpoint auth |
| `WATCH_DEBOUNCE` | `60` | Seconds to debounce notes watcher |
| `GITHUB_TOKEN` | — | For cloning private repos |
| `WEBHOOK_SECRET` | — | GitHub webhook signature validation |

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

Built at index time from AST import edges (no LLM needed):

- **Import edges** — `import`/`from` (Python), `import`/`require` (JS/TS), `use` (Rust)
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

### Dashboard — Graph tab

Web UI Graph tab: select repo → load force-directed D3.js graph. Nodes sized by centrality, colored by community. Click node to see imports detail.

## Volume paths

- Ollama models: `/mnt/data/ai/ollama` (RAID)
- Qdrant storage: `/home/docker/volumes/qdrant/storage`
- Notes (read-only mount from Syncthing): `/home/docker/volumes/syncthing/notes`
- Graph data: `/app/data/` (inside container, via cortex-mcp volume)
