#!/usr/bin/env python3
"""Cortex onboarding template and CLAUDE.md merge logic."""

import re


def _build_cortex_section(repo_names: list) -> str:
    repos_str = ", ".join(repo_names) if repo_names else "none indexed yet"
    return (
        "## Cortex\n\n"
        "Search before asking — notes vault, server config, and source code are all indexed.\n\n"
        f"- `search_notes(query)` — projects, plans, server setup, decisions\n"
        f"- `search_code(query)` — repos: {repos_str}\n"
        "- `get_neighbors(file, repo)` / `get_community(repo, id)` — dependency graph traversal\n"
        "- Not connected: `claude mcp add cortex --transport sse https://cortex.hyvitech.org/sse`\n\n"
        "## Preferences\n\n"
        "- Caveman mode — terse, fragments OK, no filler (install: `claude skill add caveman:caveman`)\n"
        "- Prefix bash with `rtk` for token savings (install: `cargo install rtk`)\n"
        '- Git: `git config user.name "Xoudusz" && git config user.email "da@w23.at"` — no co-author on commits\n'
    )


_DEFAULT_REPOS = [
    "weakness-dex", "mtgdle", "tower-of-evolon", "tower-of-evolon-backend",
    "svelte-radio", "cortex", "riftracoons",
]

CORTEX_MERGE_SECTION = _build_cortex_section(_DEFAULT_REPOS)

PROJECT_CLAUDE_MD_TEMPLATE = (
    "# [Project Name]\n\n"
    "[One-line description of what this project does.]\n\n"
    "## Stack\n\n"
    "- [language/runtime + version]\n"
    "- [framework]\n"
    "- [database/storage]\n"
    "- [deployment target]\n\n"
    "## Commands\n\n"
    "```bash\n# Development\n\n\n# Test\n\n\n# Build / lint / typecheck\n\n```\n\n"
    "## Structure\n\n"
    "```\n[key dirs/files and what they contain]\n```\n\n"
    "## Conventions\n\n"
    "- [non-obvious naming, patterns, or architectural decisions]\n\n"
    "## Don't\n\n"
    "- [anti-pattern] — do [preferred approach] instead\n\n"
    "__CORTEX_SECTION__"
)


def _merge_onboarding(existing: str, force: bool = False, repo_names: list = None) -> str:
    """Append or replace Cortex+Preferences sections in existing CLAUDE.md."""
    section = _build_cortex_section(repo_names if repo_names is not None else _DEFAULT_REPOS)
    if "## cortex" in existing.lower():
        if not force:
            return existing + "\n\n<!-- Cortex onboarding: already present -->"
        cleaned = re.sub(
            r"(?ms)^## (?:Cortex|Preferences)\b.*?(?=^## (?!(?:Cortex|Preferences)\b)|\Z)",
            "",
            existing,
        ).rstrip()
        return cleaned + "\n\n" + section
    return existing.rstrip() + "\n\n" + section
