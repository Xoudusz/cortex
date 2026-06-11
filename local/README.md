# cortex-local

Local semantic search MCP server for Claude Code — index your notes and code, search them semantically without any server or cloud dependency.

## Install

```bash
pipx install cortex-local
cortex install
```

`cortex install` downloads embedding models and registers the MCP server in Claude Code. Restart Claude Code after.

## Usage

```bash
cortex index ~/notes          # index Obsidian vault
cortex index ~/projects/myapp # index a code repo
```

Then in Claude Code, `search_notes` and `search_code` are available as MCP tools.

## How it works

- **Embeddings**: fastembed (`nomic-embed-text-v1.5`) + BM25 sparse — runs fully local, no GPU needed
- **Vector store**: embedded Qdrant at `~/.cortex/qdrant`
- **Graph layer**: import graph with degree centrality re-ranking + Personalized PageRank for notes

Full documentation: [github.com/Xoudusz/cortex](https://github.com/Xoudusz/cortex)
