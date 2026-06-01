#!/usr/bin/env python3
"""Cortex onboarding template and CLAUDE.md merge logic."""

ONBOARDING_TEMPLATE = '''# Cortex Onboarding

## MCP Setup (if not connected)
```bash
claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse
```
OAuth login will open in browser on first connection.

## Cortex Tools
Use PROACTIVELY — search before asking user for context.

- `search_notes(query)` — Obsidian vault (projects, plans, server config, decisions)
- `search_code(query)` — repos: weakness-dex, mtgdle, tower-of-evolon, tower-of-evolon-backend, svelte-radio, cortex, riftracoons
- `get_neighbors(file, repo)` — show what a file imports and what imports it
- `get_community(repo, community_id)` — list all files in the same structural cluster
- `reindex(notes, code, repo)` — refresh vectors if stale
- `reindex_status()` — check progress

## Preferences

### Communication
- Caveman mode: terse, no filler, fragments OK
- Install if missing: `claude skill add caveman:caveman`

### Commands
- Always prefix bash with `rtk` for token savings
- Install if missing: `cargo install rtk`

### Git
- User: Xoudusz <da@w23.at>
- No co-author line on commits
- Set per-repo: `git config user.name "Xoudusz" && git config user.email "da@w23.at"`
'''


def _merge_onboarding(existing: str) -> str:
    """Merge missing Cortex onboarding sections into an existing CLAUDE.md string.

    Checks for each section marker; appends only sections not already present.
    Returns the merged string, or the original with a comment if nothing was added.
    """
    sections = {
        "## MCP Setup": "## MCP Setup (if not connected)",
        "## Cortex Tools": "## Cortex Tools",
        "## Preferences": "## Preferences",
    }
    result = existing.rstrip()
    added = []
    for marker, full_header in sections.items():
        if marker.lower() in existing.lower() or "cortex" in existing.lower() and "search_notes" in existing.lower():
            continue
        template_lines = ONBOARDING_TEMPLATE.split("\n")
        in_section = False
        section_content = []
        for line in template_lines:
            if line.startswith(full_header) or line.startswith(marker):
                in_section = True
                section_content.append(line)
            elif in_section and line.startswith("## "):
                break
            elif in_section:
                section_content.append(line)
        if section_content:
            added.append("\n".join(section_content).rstrip())
    if not added:
        return existing + "\n\n<!-- Cortex onboarding: all sections already present -->"
    if "# cortex" not in existing.lower() and "## cortex" not in existing.lower():
        result += "\n\n# Cortex Onboarding"
    result += "\n\n" + "\n\n".join(added)
    return result
