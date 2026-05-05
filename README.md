# cortex

Personal RAG stack — Obsidian notes + source code indexed into Qdrant, exposed as an MCP SSE server for Claude Code.

## Services

| Service | Port | Description |
|---------|------|-------------|
| Ollama | 11434 | Embeddings via `nomic-embed-text` |
| Qdrant | 6333 | Vector store — collections: `notes`, `code` |
| cortex-mcp | 8765 | MCP SSE server for Claude Code |

## Deploy (Portainer)

1. Stacks → Add Stack → Repository
2. URL: `https://github.com/Xoudusz/cortex`
3. Auth: `Xoudusz` / PAT (Contents: Read)
4. Compose path: `docker-compose.yml`
5. Deploy

**Post-deploy — pull embedding model:**
```bash
docker exec ollama ollama pull nomic-embed-text
```

**Post-deploy — index everything:**
```bash
docker compose --profile index run --rm cortex-indexer
```
Set `GITHUB_TOKEN` env var in Portainer stack settings to clone private repos.

## Register MCP in Claude Code (run on vibecode)

```bash
claude mcp remove notes-search 2>/dev/null; true
claude mcp add cortex --transport sse http://cortex.local.hyvitech.org:8765/sse
```

## Re-index

Run any time notes or code change:
```bash
docker compose --profile index run --rm cortex-indexer
```

## Qdrant collections

| Collection | Chunk strategy | Key payload fields |
|------------|---------------|-------------------|
| `notes` | H1-H3 heading boundaries | `file`, `heading`, `tags`, `modified_at`, `text` |
| `code` | 30-line sliding window (5-line overlap) | `repo`, `file`, `language`, `start_line`, `end_line`, `github_url`, `text` |

## Volume paths

- Ollama models: `/mnt/data/ai/ollama` (RAID)
- Qdrant storage: `/home/docker/volumes/qdrant/storage`
- Notes (read-only mount from Syncthing): `/home/docker/volumes/syncthing/notes`
