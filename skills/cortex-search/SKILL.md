---
name: cortex-search
description: >
  Use cortex MCP tools to semantically search code and notes.
  Trigger when: asked about code in indexed repos, asked about notes/knowledge,
  exploring file relationships, or before writing code in an indexed repo.
---

# cortex search

## When to use

- User asks how something works in an indexed repo → `search_code`
- User asks about notes, decisions, or knowledge → `search_notes`
- Need to explore what a file imports or what imports it → `get_neighbors`
- Need all files in the same structural cluster → `get_community`
- About to write code in an indexed repo → search first, match existing patterns

## Tools

| Tool | Use for |
|------|---------|
| `search_code` | Semantic code search across indexed repos |
| `search_notes` | Semantic search across Obsidian/markdown notes |
| `get_neighbors` | Show a file's imports + what imports it |
| `get_community` | List all files in the same structural community |
| `get_stats` | Cortex efficiency metrics |
| `get_onboarding` | Repo-specific onboarding context |

## Rules

- Always call `search_code` before writing code for an indexed repo — don't guess at patterns
- Results include `file`, `lines`, `score`, `centrality` — prefer high-centrality files (core modules)
- `get_neighbors` needs exact file path and repo name: `get_neighbors("src/lib/api.ts", "my-repo")`
- `get_community` needs repo name + community_id (from search result): `get_community("my-repo", 0)`
- Search is semantic — use descriptive queries, not exact symbol names

## Example queries

```
search_code("authentication token validation")
search_notes("meeting notes architecture decision")
get_neighbors("server/mcp/tools.py", "cortex")
get_community("cortex", 12)
```
