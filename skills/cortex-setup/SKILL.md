---
name: cortex-setup
description: >
  First-time cortex setup guide.
  Use when: cortex MCP is not connected, user asks how to install cortex,
  or session-start hook reports cortex is not installed.
---

# cortex setup

## Option A — Local mode (recommended for personal use)

Runs entirely on your machine. No server needed.

```bash
# 1. Install cortex
pipx install cortex-local

# 2. Register MCP + pull embedding models (one shot)
cortex install

# 3. Index a project
cortex index /path/to/your/repo

# 4. Restart Claude Code — search tools active
```

**Ancient CPU (no SSE4.2)?**
```bash
pipx install "cortex-local[legacy]" --python python3.12
cortex install
```

## Option B — Server mode (shared / always-on)

Runs in Docker. Multiple users or machines can share one index.

```bash
# 1. Clone repo and deploy
git clone https://github.com/Xoudusz/cortex
cd cortex
docker compose up -d

# 2. Register MCP in Claude Code
claude mcp add cortex -s user --transport sse http://your-server:8765/sse

# 3. Index repos via indexer container
docker compose --profile index run --rm cortex-indexer
```

## Verify connection

After setup, start a new Claude Code session. The session-start hook will print:
```
[cortex] connected — search_code, search_notes, get_neighbors, get_community, reindex ready
```

If you see "not installed", run `cortex install` and restart.

## Indexed repos

Use `get_onboarding()` to see which repos are currently indexed and their stats.
