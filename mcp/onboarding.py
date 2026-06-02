#!/usr/bin/env python3
"""Cortex onboarding template and CLAUDE.md merge logic."""

PROJECT_CLAUDE_MD_TEMPLATE = '''# [Project Name]

[One-line description of what this project does.]

## Stack

- [language/runtime + version]
- [framework]
- [database/storage]
- [deployment target]

## Commands

```bash
# Development


# Test


# Build / lint / typecheck

```

## Structure

```
[key dirs/files and what they contain]
```

## Conventions

- [non-obvious naming, patterns, or architectural decisions]

## Don\'t

- [anti-pattern] — do [preferred approach] instead

## Cortex

Search before asking — notes vault, server config, and source code are all indexed.

- `search_notes(query)` — projects, plans, server setup, decisions
- `search_code(query)` — repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex, riftracoons
- `get_neighbors(file, repo)` / `get_community(repo, id)` — dependency graph traversal
- Not connected: `claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse`

## Preferences

- Caveman mode — terse, fragments OK, no filler (install: `claude skill add caveman:caveman`)
- Prefix bash with `rtk` for token savings (install: `cargo install rtk`)
- Git: `git config user.name "Xoudusz" && git config user.email "da@w23.at"` — no co-author on commits
'''

CORTEX_MERGE_SECTION = '''## Cortex

Search before asking — notes vault, server config, and source code are all indexed.

- `search_notes(query)` — projects, plans, server setup, decisions
- `search_code(query)` — repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex, riftracoons
- `get_neighbors(file, repo)` / `get_community(repo, id)` — dependency graph traversal
- Not connected: `claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse`

## Preferences

- Caveman mode — terse, fragments OK, no filler (install: `claude skill add caveman:caveman`)
- Prefix bash with `rtk` for token savings (install: `cargo install rtk`)
- Git: `git config user.name "Xoudusz" && git config user.email "da@w23.at"` — no co-author on commits
'''


def _merge_onboarding(existing: str) -> str:
    """Append Cortex section to existing CLAUDE.md if not already present."""
    if "## cortex" in existing.lower():
        return existing + "\n\n<!-- Cortex onboarding: already present -->"
    return existing.rstrip() + "\n\n" + CORTEX_MERGE_SECTION
