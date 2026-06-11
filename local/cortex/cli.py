"""cortex CLI — index <path> and serve (stdio MCP)."""

import shutil
import subprocess
import sys
from pathlib import Path

import click

from .config import (
    WORKSPACES_DIR, get_active_workspace, set_active_workspace, get_workspace_dir,
)


@click.group()
def cli() -> None:
    """cortex: local semantic search MCP server."""


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
def index(path: str) -> None:
    """Index PATH (notes and/or code) into ~/.cortex."""
    from .indexer import index_path
    index_path(Path(path))


@cli.command()
def serve() -> None:
    """Run cortex MCP server on stdio."""
    from .mcp_server import run
    run()


@cli.command()
def pull_models() -> None:
    """Pre-download fastembed models."""
    from .embedder import pull_models as _pull
    _pull()


@cli.command()
def stats() -> None:
    """Show cortex efficiency stats."""
    from .state import _stats
    from .mcp_server import _fmt_stats
    from .config import VERSION
    click.echo(_fmt_stats(VERSION, _stats, current=True))


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


@cli.command("install")
def install_cmd() -> None:
    """Download embedding models and register cortex MCP in Claude Code."""
    from .embedder import pull_models as _pull
    click.echo("Downloading embedding models...")
    _pull()
    mcp_cmd = "claude mcp add cortex --transport stdio cortex serve"
    claude = shutil.which("claude")
    if not claude:
        click.echo("Models ready. Register MCP manually (claude not found in PATH):")
        click.echo(f"  {mcp_cmd}")
        return
    click.echo("Registering MCP server in Claude Code...")
    result = subprocess.run(
        [claude, "mcp", "add", "cortex", "--transport", "stdio", "cortex", "serve"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.echo("Done. cortex is ready — restart Claude Code to activate.")
    else:
        click.echo(f"MCP registration failed. Run manually:\n  {mcp_cmd}")
        click.echo(result.stderr.strip())
