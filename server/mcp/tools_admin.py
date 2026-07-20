#!/usr/bin/env python3
"""Admin/management tools for cortex MCP server."""

import time

from qdrant_client import QdrantClient

from config import QDRANT_URL, VERSION, collection_name
from state import _stats, _get_code_graph_meta, _load_all_stats, get_active_workspace, set_active_workspace, _workspace_data_dir
from onboarding import PROJECT_CLAUDE_MD_TEMPLATE, CORTEX_MERGE_SECTION, _merge_onboarding
from reindex import _enqueue, get_status, clear_cache as _clear_cache
from repos import _load_repos
from formatters import fmt_stats


def register_admin(mcp) -> None:
    @mcp.tool()
    def reindex(notes: bool = True, code: bool = True, repo: str = "", force: bool = False) -> str:
        """Trigger re-indexing of notes and/or source code into Qdrant.

        Use when:
        - search_notes or search_code returns stale or missing results
        - The user says they updated their notes or pushed new code
        - Starting a session after a long gap (index may be outdated)

        Runs async — returns immediately. Call reindex_status() to check progress.
        Set notes=False to only reindex code, or code=False for notes only.
        Set repo to a specific repo name (e.g. "svelte-radio") to only reindex that repo.
        Set force=True to clear the embed cache first (re-embeds all files, ~10x slower).
        """
        _enqueue(notes, code, repo, files=None, force=force)
        q = get_status()["queue_depth"]
        prefix = "Force reindex" if force else "Reindex"
        return f"{prefix} queued (position {q}). Use reindex_status() to check progress."

    @mcp.tool()
    def clear_cache(all_workspaces: bool = False) -> str:
        """Clear the embed cache so the next reindex re-embeds all files from scratch.

        Use after deploying chunker or embedding changes that require fresh embeddings.
        Does NOT trigger a reindex — call reindex() after this if needed.
        Set all_workspaces=True to clear cache for every workspace (not just active one).
        WARNING: next reindex after clearing will be ~10x slower than normal.
        """
        n = _clear_cache(all_workspaces=all_workspaces)
        scope = "all workspaces" if all_workspaces else "current workspace"
        if n == 0:
            return f"No cache files found for {scope} (already clean)."
        return f"Cleared {n} cache file(s) for {scope}. Run reindex() to rebuild from scratch."

    @mcp.tool()
    def reindex_status(monitor: bool = False) -> str:
        """Check whether a reindex is running or finished, and see its output log.

        Set monitor=True to auto-monitor: if still running, returns a ScheduleWakeup
        instruction so Claude polls every 60s and sends a PushNotification when done.
        """
        s = get_status()
        q = s.get("queue_depth", 0)
        if s["started_at"] is None:
            idle = "No reindex has been run yet."
            return idle + (f" {q} jobs queued." if q else "")
        elapsed = time.time() - s["started_at"]
        status = "running" if s["running"] else "done"
        header = f"Status: {status} ({elapsed:.0f}s elapsed)"
        if q:
            header += f" — {q} more job(s) queued"
        lines = [header]
        if s["output"]:
            lines.append("\n".join(s["output"]))
        if s["error"]:
            lines.append(f"Error: {s['error']}")
        result = "\n\n".join(lines)
        if monitor and (s["running"] or q > 0):
            result += (
                "\n\nMONITOR INSTRUCTION: Call ScheduleWakeup immediately with:\n"
                "- delaySeconds: 60\n"
                "- prompt: \"Call the cortex reindex_status MCP tool with monitor=True. "
                "If still running (running=True or queue_depth>0), the tool will instruct you to reschedule. "
                "If done, call PushNotification with a one-line summary and stop.\""
            )
        elif monitor and not s["running"] and q == 0:
            result += "\n\nMONITOR: Reindex already done — no scheduling needed."
        return result

    @mcp.tool()
    def get_stats(all: bool = False) -> str:
        """Return cortex efficiency metrics.

        all=False (default): current version stats with uptime, search mix, PPR effectiveness, cache, centrality lift.
        all=True: all persisted versions side-by-side for comparison.
        """
        if all:
            versions = _load_all_stats()
            if not versions:
                return "No persisted stats found. Stats save every 60s."
            blocks = []
            for v in sorted(versions):
                blocks.append(fmt_stats(v, versions[v], current=(v == VERSION)))
            return "=== All versions ===\n\n" + "\n\n".join(blocks)

        queue_depth = get_status().get("queue_depth", 0)
        out = fmt_stats(VERSION, _stats, current=True)
        if queue_depth:
            out += f"\n  reindex queue depth: {queue_depth}"
        return out

    @mcp.tool()
    def get_neighbors(file: str, repo: str) -> str:
        """Show what a code file imports and what imports it (direct graph neighbors).

        Use when you want to explore structural connections around a file you found.
        Example: get_neighbors("mcp/server.py", "cortex")

        Requires graph data — run reindex first if empty.
        """
        meta = _get_code_graph_meta(repo)
        if not meta:
            return f"No graph data for '{repo}'. Run reindex(code=True, repo='{repo}') first."
        file_meta = meta.get(file)
        if file_meta is None:
            matches = [f for f in meta if file in f]
            if not matches:
                return f"File '{file}' not found in graph for '{repo}'."
            file = matches[0]
            file_meta = meta[file]
        imports = file_meta.get("imports", [])
        imported_by = file_meta.get("imported_by", [])
        lines = [
            f"**{file}**",
            f"centrality: {file_meta.get('centrality', 0)} · community: {file_meta.get('community_id', '?')}",
        ]
        if imports:
            lines.append(f"\nimports ({len(imports)}):")
            lines.extend(f"  -> {f}" for f in imports)
        if imported_by:
            lines.append(f"\nimported by ({len(imported_by)}):")
            lines.extend(f"  <- {f}" for f in imported_by)
        if not imports and not imported_by:
            lines.append("\nNo connections found (isolated file).")
        return "\n".join(lines)

    @mcp.tool()
    def get_community(repo: str, community_id: int) -> str:
        """List all files in the same structural community/cluster for a repo.

        Use when you want to find everything structurally related to a file.
        Tip: run search_code first to find a community_id, then call this.
        Example: get_community("cortex", 0)

        Requires graph data — run reindex first if empty.
        """
        meta = _get_code_graph_meta(repo)
        if not meta:
            return f"No graph data for '{repo}'. Run reindex(code=True, repo='{repo}') first."
        members = [
            (f, m.get("centrality", 0))
            for f, m in meta.items()
            if m.get("community_id") == community_id
        ]
        if not members:
            return f"Community {community_id} not found in '{repo}'."
        members.sort(key=lambda x: -x[1])
        lines = [f"**Community {community_id}** in '{repo}' — {len(members)} files:"]
        for f, centrality in members:
            star = "*" if centrality > 0.1 else " "
            lines.append(f"  {star} {f} (centrality: {centrality})")
        return "\n".join(lines)

    @mcp.tool()
    def switch_workspace(name: str) -> str:
        """Switch the active cortex workspace.

        Each workspace has its own isolated Qdrant collections and repos list.
        Use when switching between work/personal/project contexts.
        Example: switch_workspace("work")
        """
        client = QdrantClient(url=QDRANT_URL)
        existing = {c.name for c in client.get_collections().collections}
        code_coll = collection_name("code", name)
        notes_coll = collection_name("notes", name)
        has_index = code_coll in existing or notes_coll in existing
        if not has_index and name != "default":
            return (
                f"Workspace '{name}' has no indexed collections ({code_coll}, {notes_coll}).\n"
                f"Index it first with reindex(), then switch."
            )
        set_active_workspace(name)
        repos = _load_repos(name)
        repo_names = [r.split("/")[-1] for r in repos]
        return (
            f"Switched to workspace '{name}'. "
            f"search_code and search_notes now use {code_coll}/{notes_coll}.\n"
            f"Repos: {', '.join(repo_names) if repo_names else 'none'}"
        )

    @mcp.tool()
    def list_workspaces() -> str:
        """List all cortex workspaces and their status.

        Shows which workspace is currently active and whether each has indexed collections.
        """
        client = QdrantClient(url=QDRANT_URL)
        existing = {c.name for c in client.get_collections().collections}
        active = get_active_workspace()

        workspaces: dict = {"default": {"code": "code", "notes": "notes"}}
        for coll in existing:
            if "_" in coll:
                parts = coll.rsplit("_", 1)
                if parts[1] in ("code", "notes"):
                    ws = parts[0]
                    if ws not in workspaces:
                        workspaces[ws] = {}
                    workspaces[ws][parts[1]] = coll

        lines = [f"Active workspace: {active}\n"]
        for ws in sorted(workspaces):
            marker = "* " if ws == active else "  "
            colls = workspaces[ws]
            has_code = colls.get("code", "") in existing
            has_notes = colls.get("notes", "") in existing
            status = []
            if has_code:
                status.append("code")
            if has_notes:
                status.append("notes")
            indexed = f"indexed: {', '.join(status)}" if status else "empty"
            lines.append(f"{marker}{ws} ({indexed})")
        return "\n".join(lines)

    @mcp.tool()
    def get_onboarding(existing_content: str = "") -> str:
        """Get a project CLAUDE.md template, or merge Cortex section into existing content.

        No args: returns full PROJECT_CLAUDE_MD_TEMPLATE with placeholder sections
        (Stack, Commands, Structure, Conventions, Don't) that Claude should fill in
        by examining the actual codebase. Cortex and Preferences sections are pre-filled.

        With existing_content: appends Cortex + Preferences sections if not already present.
        """
        if existing_content.strip():
            return _merge_onboarding(existing_content)
        return PROJECT_CLAUDE_MD_TEMPLATE

    @mcp.prompt()
    def onboarding() -> str:
        """Set up Cortex and user preferences for this project."""
        return """Set up Cortex for this project. Execute this checklist in order:

## 1. CLAUDE.md
- Read existing CLAUDE.md if present; pass its content to `get_onboarding(existing_content)`.
- If no CLAUDE.md exists, call `get_onboarding()` with no args.
- Write the result to CLAUDE.md.
- Fill in the placeholder sections (Stack, Commands, Structure, Conventions, Don't)
  by examining the actual codebase (package.json / requirements.txt / Cargo.toml / go.mod,
  directory listing, existing README, etc.).

## 2. Git Config
```bash
rtk git config user.name "Xoudusz" && rtk git config user.email "da@w23.at"
```

## 3. RTK
Run `rtk --version`. If command not found: `cargo install rtk`

## 4. Caveman Skill
Run `claude skill list`. If `caveman:caveman` missing: `claude skill add caveman:caveman`

## 5. Verify Cortex
Call `search_notes("test")`. Report pass/fail for each step above."""
