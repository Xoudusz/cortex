"""cortex CLI — index <path> and serve (stdio MCP)."""

import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import click

from .config import (
    WORKSPACES_DIR, get_active_workspace, set_active_workspace, get_workspace_dir,
    data_dir, save_last_indexed_path, qdrant_path, get_config, VERSION, MODELS_DIR,
)


@click.group()
@click.version_option(VERSION, prog_name="cortex")
def cli() -> None:
    """cortex: local semantic search MCP server."""
    # Windows consoles default to cp1252; never crash on non-ASCII output (e.g. `claude mcp get`).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--progress/--no-progress", default=None,
              help="Show tqdm progress bar (default: only when stderr is a terminal).")
def index(path: str, progress: bool) -> None:
    """Index PATH (notes and/or code) into ~/.cortex."""
    import logging
    from .indexer import index_path
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)
    if progress is None:
        progress = sys.stderr.isatty()
    index_path(Path(path), show_progress=progress)
    save_last_indexed_path(path)


@cli.command()
def serve() -> None:
    """Run cortex MCP server on stdio."""
    # stdout is the MCP channel: startup failures go to stderr (shown by `claude mcp get` / logs)
    # instead of dying silently as "Connection closed".
    try:
        from .mcp_server import run
    except Exception:
        import traceback
        sys.stderr.write(f"cortex {VERSION}: failed to start (import error):\n{traceback.format_exc()}")
        sys.stderr.write("Try reinstalling: pipx install --force cortex-local\n")
        sys.exit(1)
    try:
        run()
    except KeyboardInterrupt:
        pass
    except Exception:
        import logging
        import traceback
        logging.getLogger("cortex").exception("server crashed")
        sys.stderr.write(f"cortex {VERSION}: server error:\n{traceback.format_exc()}")
        sys.exit(1)


@cli.command()
def pull_models() -> None:
    """Pre-download fastembed models."""
    from .embedder import pull_models as _pull
    _pull()


@cli.command()
def stats() -> None:
    """Show cortex efficiency stats."""
    from .state import _stats
    from .core.formatters import fmt_stats
    from .config import VERSION
    click.echo(fmt_stats(VERSION, _stats, current=True))


@cli.group()
def workspace() -> None:
    """Manage cortex workspaces."""


@workspace.command("list")
def workspace_list() -> None:
    """List all workspaces and their status."""
    active = get_active_workspace()
    if not WORKSPACES_DIR.exists():
        click.echo(f"No workspaces found. Active: '{active}' (not yet indexed).")
        return
    workspaces = sorted([d.name for d in WORKSPACES_DIR.iterdir() if d.is_dir()])
    if not workspaces:
        click.echo(f"No workspaces found. Active: '{active}'.")
        return
    click.echo(f"Active workspace: {active}\n")
    for ws in workspaces:
        marker = "* " if ws == active else "  "
        has_index = (WORKSPACES_DIR / ws / "qdrant").exists()
        click.echo(f"{marker}{ws} ({'indexed' if has_index else 'empty'})")


@workspace.command("create")
@click.argument("name")
def workspace_create(name: str) -> None:
    """Create a new workspace."""
    ws_dir = get_workspace_dir(name)
    if ws_dir.exists():
        click.echo(f"Workspace '{name}' already exists.")
        return
    ws_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Created workspace '{name}'. Switch with: cortex workspace switch {name}")


@workspace.command("switch")
@click.argument("name")
def workspace_switch(name: str) -> None:
    """Switch the active workspace."""
    ws_dir = get_workspace_dir(name)
    if not ws_dir.exists():
        click.echo(f"Workspace '{name}' does not exist. Create it with: cortex workspace create {name}")
        return
    set_active_workspace(name)
    click.echo(f"Switched to workspace '{name}'.")


@workspace.command("delete")
@click.argument("name")
@click.confirmation_option(prompt="Delete workspace and all its data?")
def workspace_delete(name: str) -> None:
    """Delete a workspace and all its indexed data."""
    if name == get_active_workspace():
        click.echo("Cannot delete active workspace. Switch first.")
        return
    ws_dir = get_workspace_dir(name)
    if not ws_dir.exists():
        click.echo(f"Workspace '{name}' does not exist.")
        return
    shutil.rmtree(ws_dir)
    click.echo(f"Deleted workspace '{name}'.")


@workspace.command("current")
def workspace_current() -> None:
    """Print the active workspace name."""
    click.echo(get_active_workspace())


@cli.command("search-log")
@click.option("--top", default=10, show_default=True, help="Number of top queries to show.")
def search_log_cmd(top: int) -> None:
    """Show search query analytics from the search log."""
    log_file = data_dir() / "search_log.jsonl"
    if not log_file.exists():
        click.echo("No search log found. Run some searches first.")
        return
    queries = []
    zero_result_queries = []
    tool_counts: Counter = Counter()
    with open(log_file) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except Exception:
                continue
            q = entry.get("query", "")
            queries.append(q)
            tool_counts[entry.get("tool", "unknown")] += 1
            if not entry.get("top"):
                zero_result_queries.append(q)
    if not queries:
        click.echo("Search log is empty.")
        return
    click.echo(f"Total searches: {len(queries)}")
    for tool, count in sorted(tool_counts.items()):
        click.echo(f"  {tool}: {count}")
    click.echo(f"\nTop {top} queries:")
    for q, n in Counter(queries).most_common(top):
        click.echo(f"  {n:3d}x  {q}")
    if zero_result_queries:
        unique_zero = sorted(set(zero_result_queries))
        click.echo(f"\nZero-result queries ({len(unique_zero)} unique):")
        for q in unique_zero[:20]:
            click.echo(f"  {q}")


_SYSTEM_PREFIXES = [Path(p) for p in ("/usr", "/bin", "/etc", "/sbin", "/var", r"C:\Windows")]
_SCOPE_CHOICES = click.Choice(["user", "local", "project"])


def _is_system_dir(p: Path) -> bool:
    r = p.resolve()
    if r == Path("/"):
        return True
    return any(prefix.exists() and r.is_relative_to(prefix) for prefix in _SYSTEM_PREFIXES)


@cli.command("install")
@click.option("--scope", default="user", type=_SCOPE_CHOICES, show_default=True,
              help="MCP registration scope.")
def install_cmd(scope: str) -> None:
    """Download embedding models and register cortex MCP in Claude Code."""
    from .embedder import pull_models as _pull
    cwd = Path.cwd()
    if scope != "user" and _is_system_dir(cwd):
        click.echo(f"Warning: cwd looks like a system directory ({cwd}). Use --scope user to register globally.")
    click.echo("Downloading embedding models...")
    _pull()
    mcp_cmd = f"claude mcp add --scope {scope} cortex --transport stdio cortex serve"
    claude = shutil.which("claude")
    if not claude:
        click.echo("Models ready. Register MCP manually (claude not found in PATH):")
        click.echo(f"  {mcp_cmd}")
        return
    click.echo("Registering MCP server in Claude Code...")
    subprocess.run(
        [claude, "mcp", "remove", "cortex", "--scope", scope],
        capture_output=True, text=True,
    )
    result = subprocess.run(
        [claude, "mcp", "add", "--scope", scope, "cortex", "--transport", "stdio", "cortex", "serve"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.echo(f"Done. cortex is ready (scope: {scope}) - restart Claude Code to activate.")
    else:
        click.echo(f"MCP registration failed. Run manually:\n  {mcp_cmd}")
        click.echo(result.stderr.strip())


@cli.command("uninstall")
@click.option("--scope", default="user", type=_SCOPE_CHOICES, show_default=True,
              help="MCP registration scope to remove from.")
def uninstall_cmd(scope: str) -> None:
    """Remove cortex MCP registration from Claude Code."""
    claude = shutil.which("claude")
    if not claude:
        click.echo(f"claude not found in PATH. Remove manually:\n  claude mcp remove cortex --scope {scope}")
        return
    result = subprocess.run(
        [claude, "mcp", "remove", "cortex", "--scope", scope],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.echo(f"cortex MCP removed (scope: {scope}).")
    else:
        click.echo(f"Removal failed (scope: {scope}).")
        click.echo(result.stderr.strip())


@cli.command("doctor")
def doctor_cmd() -> None:
    """Show cortex status: version, model cache, MCP registration, workspace, index."""
    click.echo(f"version      {VERSION}")

    cache_ok = MODELS_DIR.exists() and any(MODELS_DIR.iterdir())
    click.echo(f"model cache  {'ok' if cache_ok else 'missing - run: cortex pull-models'}")

    claude = shutil.which("claude")
    mcp_status = "claude not found in PATH"
    if claude:
        r = subprocess.run([claude, "mcp", "get", "cortex"], capture_output=True, text=True)
        if r.returncode == 0:
            fields = {}
            for line in r.stdout.splitlines():
                key, sep, val = line.strip().partition(":")
                if sep and key in ("Scope", "Status"):
                    fields[key] = val.strip()
            mcp_status = ", ".join(f"{k.lower()}: {v}" for k, v in fields.items()) or "registered"
        else:
            mcp_status = "not registered - run: cortex install"
    click.echo(f"MCP          {mcp_status}")

    ws = get_active_workspace()
    indexed = Path(qdrant_path(ws)).exists()
    click.echo(f"workspace    {ws} ({'indexed' if indexed else 'not indexed'})")

    last = get_config()["index"].get("last_path") or "(none)"
    click.echo(f"last indexed {last}")
    from .config import read_index_meta
    from .core.formatters import fmt_index_roots
    roots = read_index_meta(ws).get("roots", {})
    for line in fmt_index_roots(roots):
        root = line.split(" ", 1)[0]
        click.echo(f"root         {line}{'' if Path(root).exists() else ' (missing on disk)'}")
    if indexed and not roots:
        click.echo("note         index has no recorded roots - run: cortex index <path>")

    claude_json = Path.home() / ".claude.json"
    if claude_json.exists():
        try:
            projects = json.loads(claude_json.read_text()).get("projects", {})
            stale = [p for p, v in projects.items() if "cortex" in v.get("mcpServers", {})]
            if stale:
                click.echo("\nStale local registrations (run from each dir to remove):")
                for p in stale:
                    click.echo(f"  cd {p} && claude mcp remove cortex --scope local")
        except Exception:
            pass
