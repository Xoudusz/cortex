"""cortex CLI — index <path> and serve (stdio MCP)."""

import subprocess
import sys
from pathlib import Path

import click


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


@cli.command("install")
def install_cmd() -> None:
    """Download embedding models and register cortex MCP in Claude Code."""
    from .embedder import pull_models as _pull
    click.echo("Downloading embedding models...")
    _pull()
    click.echo("Registering MCP server in Claude Code...")
    result = subprocess.run(
        ["claude", "mcp", "add", "cortex", "--transport", "stdio", "cortex", "serve"],
        capture_output=True, text=True,
        shell=(sys.platform == "win32"),
    )
    if result.returncode == 0:
        click.echo("Done. cortex is ready — restart Claude Code to activate.")
    else:
        click.echo(f"MCP registration failed:\n{result.stderr}")
        click.echo("Run manually: claude mcp add cortex --transport stdio cortex serve")
        sys.exit(1)
