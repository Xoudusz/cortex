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

```bash
pipx install cortex-local
cortex install   # pulls models + registers MCP in Claude Code
```

Restart Claude Code. Then index your projects:

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
| `switch_workspace(name)` | Switch active workspace (isolated collections + repos) |
| `list_workspaces()` | List all workspaces and their index status |

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

OAuth login opens in browser on first connection. Tokens persist (30-day access, 90-day refresh). Running Claude Code on a remote server? Cortex relays the OAuth callback server-side — no manual URL replacement needed.

**Environment variables:**

| Var | Default | Purpose |
|-----|---------|---------|
| `ADMIN_PASSWORD` | — | Required — OAuth login password |
| `BASE_URL` | `http://localhost:8765` | Public URL for OAuth metadata |
| `GITHUB_TOKEN` | — | For listing/cloning private repos. Use a **classic PAT with `repo` scope** for repos you collaborate on. Dashboard Admin → Settings overrides it |
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

## Supported languages

| Language | Extensions | Chunking |
|----------|-----------|---------|
| Python | `.py` | Semantic (tree-sitter) |
| JavaScript | `.js`, `.jsx` | Semantic (tree-sitter) |
| TypeScript | `.ts`, `.tsx` | Semantic (tree-sitter) |
| Kotlin | `.kt`, `.kts` | Semantic (tree-sitter) |
| GDScript | `.gd` | Semantic (tree-sitter): functions, inner classes, member blocks; `@annotations` kept with their declaration; `class_name`/`extends` as context |
| Godot scenes/resources/project | `.tscn`, `.tres`, `project.godot` | Summary: node tree + scripts + instances + signal connections / resource type + properties / autoloads, main scene, input actions |
| Godot text | `.gdshader`, `.dialogue` | Sliding window |
| C# | `.cs` | Semantic (tree-sitter) |
| Svelte | `.svelte` | Sliding window |
| Java | `.java` | Sliding window |
| Go | `.go` | Sliding window |
| Rust | `.rs` | Sliding window |
| GDScript | `.gd` | Sliding window |
| CSS | `.css` | Sliding window |
| HTML | `.html` | Sliding window |
| YAML | `.yml`, `.yaml` | Sliding window |

Semantic chunking splits files by function/class/method boundaries. Sliding window uses fixed-size overlapping chunks as a fallback for unsupported languages.

---

## Graph layer

Graph-augmented RAG builds structural graphs at index time, then uses them to boost retrieval.

### Code graph

Built from static analysis (no LLM):

- **Import edges** — `import`/`from` (Python), `import`/`require` (JS/TS/Svelte), `import` (Kotlin). Resolves path aliases (`$lib/` → `src/lib/`).
- **Call edges** — JS/TS/Svelte: named imports matched against call sites. Kotlin: imported names that are called or used as receivers (`Foo.bar`, `Foo::class`), plus same-package classes/objects that are called
- **Inheritance edges** — `class Foo(Bar)` (Python), `extends`/`implements` (TS/Kotlin)
- **Godot** — `extends ClassName` / `extends "res://…"` (inherits), `preload`/`load("res://…")` and `.tscn`/`.tres`/`project.godot` resource references (import), `class_name` and autoload usages (call). `res://` resolves against the folder holding `project.godot`; `uid://` via `.uid` files and scene headers. `get_neighbors` accepts `res://` paths
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
eval/          # golden query set + eval harness (hit@k, MRR)
docker-compose.yml
```

---

## Auth (server mode)

Built-in OAuth 2.0 AS — no external provider needed.

- RFC 8414 (AS metadata), RFC 7591 (Dynamic Client Registration), RFC 7636 (PKCE S256)
- Authorization code + refresh token flow
- 30-day access tokens, 90-day refresh tokens
- State persists in `/app/data/oauth_state.json` across restarts

## Excluding files per repo

Put a `.cortexignore` in the repo root (gitignore-like: `addons/gut/`, `/vendor` anchored, `*.min.js`, `#` comments; no `!` negation). Directories containing a `.gdignore` (Godot) and `.godot/` are always skipped. Files that become excluded are removed from the index on the next full reindex.

