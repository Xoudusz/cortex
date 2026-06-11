# cortex-local

Local semantic search MCP server for Claude Code — index your notes and code, search them semantically without any server or cloud dependency.

## Install

```bash
pipx install cortex-local
cortex install
```

`cortex install` downloads embedding models and registers the MCP server in Claude Code. Restart Claude Code after.

### Legacy CPUs (no SSE4.2 / X86_V2)

NumPy 2.x requires SSE4.2. If you get a `RuntimeError: NumPy was built with baseline optimizations (X86_V2)` error, use the legacy extra with Python 3.12:

```bash
pipx install "cortex-local[legacy]" --python /path/to/python3.12
cortex install
```

`[legacy]` pins `numpy==1.26.4` which has no SSE4.2 requirement. Python 3.12 is required because numpy 1.26.x has no wheels for 3.13+.

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
