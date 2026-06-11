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
