#!/usr/bin/env python3
"""Global cross-repo graph — scans root config files for inter-repo references."""

import json
import os
import re
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False
    print("Warning: networkx not installed — graph features disabled")

_CROSS_REPO_CONFIG = {
    "package.json", "requirements.txt", "go.mod", "pyproject.toml",
    "Cargo.toml", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
}
_CROSS_REPO_SKIP = {
    "node_modules", ".git", "dist", "build", ".next", ".svelte-kit",
    "__pycache__", ".gradle", "target",
}


def _slug_variants(name: str) -> set:
    return {name, name.replace("-", "_"), name.replace("_", "-")}


def _find_cross_repo_refs(src_repo: str, repo_path: Path, other_repos: list) -> dict:
    """Return {dst_repo: [files]} scanning root config + .env* files for other repo name mentions."""
    if not other_repos:
        return {}
    variant_to_repo: dict = {}
    for r in other_repos:
        for v in _slug_variants(r):
            variant_to_repo[v.lower()] = r
    refs: dict = {}

    def _check(path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            return
        rel = str(path.relative_to(repo_path))
        for variant, dst in variant_to_repo.items():
            if variant in text:
                refs.setdefault(dst, [])
                if rel not in refs[dst]:
                    refs[dst].append(rel)

    for fname in _CROSS_REPO_CONFIG:
        p = repo_path / fname
        if p.exists():
            _check(p)
    for p in repo_path.glob(".env*"):
        if p.is_file():
            _check(p)
    return refs


def build_global_graph(repo_paths: dict) -> None:
    """Build graph_global.json with cross-repo edges. repo_paths = {repo_name: Path}"""
    if not _NX_AVAILABLE:
        return
    repo_names = list(repo_paths.keys())
    G = nx.DiGraph()
    G.add_nodes_from(repo_names)
    for src_repo, repo_path in repo_paths.items():
        if not repo_path.exists():
            continue
        other_repos = [r for r in repo_names if r != src_repo]
        refs = _find_cross_repo_refs(src_repo, repo_path, other_repos)
        for dst_repo, files in refs.items():
            if G.has_edge(src_repo, dst_repo):
                merged = list(set(G[src_repo][dst_repo].get("files", []) + files))
                G[src_repo][dst_repo]["files"] = merged
            else:
                G.add_edge(src_repo, dst_repo, type="cross-repo", files=files)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [{"id": n} for n in G.nodes],
        "edges": [
            {"source": u, "target": v, "type": "cross-repo", "files": d.get("files", [])}
            for u, v, d in G.edges(data=True)
        ],
    }
    out = DATA_DIR / "graph_global.json"
    out.write_text(json.dumps(data))
    print(
        f"  global graph: {len(repo_names)} repos, {len(data['edges'])} cross-repo edges -> {out.name}"
    )
