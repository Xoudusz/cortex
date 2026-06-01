#!/usr/bin/env python3
"""Shared config, state, and utilities for cortex-mcp."""

import json
import logging
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cortex")

OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL     = os.environ.get("QDRANT_URL", "http://qdrant:6333")
EMBED_MODEL    = "nomic-embed-text"
HOST           = os.environ.get("MCP_HOST", "0.0.0.0")
PORT           = int(os.environ.get("MCP_PORT", "8765"))
NOTES_PATH     = os.environ.get("NOTES_PATH", "/notes")
WATCH_DEBOUNCE = int(os.environ.get("WATCH_DEBOUNCE", "60"))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
BASE_URL       = os.environ.get("BASE_URL", "http://localhost:8765").rstrip("/")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
REPOS_CONFIG   = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
DATA_DIR       = Path(REPOS_CONFIG).parent
VERSION        = (Path("/app/VERSION").read_text().strip()
                  if Path("/app/VERSION").exists() else "dev")
STATS_FILE     = DATA_DIR / "stats.json"

DEFAULT_REPOS = [
    "Xoudusz/weakness-dex",
    "Xoudusz/mtgdle",
    "Xoudusz/tower-of-evolon",
    "Xoudusz/tower-of-evolon-backend",
    "Xoudusz/svelte-radio",
    "Xoudusz/cortex",
    "Xoudusz/riftracoons-web",
]

_webhook_log: list = []
_graph_cache: dict = {}


def _load_repos_meta() -> dict:
    try:
        if os.path.exists(REPOS_CONFIG):
            with open(REPOS_CONFIG) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"repos": data.get("repos", []), "indexed_at": data.get("indexed_at", {})}
            if isinstance(data, list) and data:
                return {"repos": data, "indexed_at": {}}
    except Exception:
        pass
    return {"repos": list(DEFAULT_REPOS), "indexed_at": {}}


def _load_repos() -> list:
    return _load_repos_meta()["repos"]


def _save_repos_meta(meta: dict) -> None:
    os.makedirs(os.path.dirname(REPOS_CONFIG) or ".", exist_ok=True)
    with open(REPOS_CONFIG, "w") as f:
        json.dump(meta, f, indent=2)


def _save_repos(repos: list) -> None:
    meta = _load_repos_meta()
    meta["repos"] = repos
    _save_repos_meta(meta)


def _update_indexed_at(repo_name: str) -> None:
    meta = _load_repos_meta()
    meta.setdefault("indexed_at", {})[repo_name] = datetime.now(timezone.utc).isoformat()
    _save_repos_meta(meta)


def _get_code_graph_meta(repo_name: str) -> dict:
    if repo_name in _graph_cache:
        _stats["graph_cache_hits"] += 1
        return _graph_cache[repo_name]
    path = DATA_DIR / f"graph_{repo_name}.json"
    if not path.exists():
        _stats["graph_cache_misses"] += 1
        return {}
    try:
        data = json.loads(path.read_text())
        meta = {n["id"]: n for n in data.get("nodes", []) if "id" in n}
        _graph_cache[repo_name] = meta
        _stats["graph_cache_misses"] += 1
        return meta
    except Exception:
        _stats["graph_cache_misses"] += 1
        return {}


def _invalidate_graph_cache(repo_name: str = "") -> None:
    if repo_name:
        _graph_cache.pop(repo_name, None)
    else:
        _graph_cache.clear()


def _default_stats() -> dict:
    return {
        "search_code_calls": 0,
        "centrality_lift_total": 0.0,
        "centrality_lift_count": 0,
        "search_notes_calls": 0,
        "ppr_fires": 0,
        "ppr_results_added": 0,
        "graph_cache_hits": 0,
        "graph_cache_misses": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_stats() -> dict:
    defaults = _default_stats()
    try:
        if STATS_FILE.exists():
            data = json.loads(STATS_FILE.read_text())
            saved = data.get("versions", {}).get(VERSION, {})
            if saved:
                return {**defaults, **saved}
    except Exception:
        pass
    return defaults


def _save_stats() -> None:
    try:
        existing: dict = {}
        if STATS_FILE.exists():
            existing = json.loads(STATS_FILE.read_text()).get("versions", {})
        existing[VERSION] = {**_stats, "last_saved": datetime.now(timezone.utc).isoformat()}
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.write_text(json.dumps({"versions": existing}, indent=2))
    except Exception as e:
        log.warning("stats save failed: %s", e)


def _stats_saver() -> None:
    while True:
        time.sleep(60)
        _save_stats()


_stats: dict = _load_stats()

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


def embed(text: str) -> list:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:4000]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def warmup() -> None:
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": "warmup"},
            timeout=20,
        )
        log.info("warmup OK")
    except Exception as e:
        log.warning("warmup failed: %s", e)
