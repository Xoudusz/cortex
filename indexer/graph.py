#!/usr/bin/env python3
"""Graph extraction, centrality, community detection, and PPR for code and notes."""

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


# ---------------------------------------------------------------------------
# Code graph (AST import edges)
# ---------------------------------------------------------------------------

_IMPORT_RE: dict = {
    "py": re.compile(r'^(?:from|import)\s+([\w.]+)', re.MULTILINE),
    "js": re.compile(r'''(?:import|from|require)\s*\(?['"](\.\.[^'"]+)['"]'''),
    "ts": re.compile(r'''(?:import|from|require)\s*\(?['"](\.\.[^'"]+)['"]'''),
    "kt": re.compile(r'^import\s+([\w.]+)', re.MULTILINE),
}
_IMPORT_RE["js"] = re.compile(r'''(?:import|from|require)\s*\(?['"](\.[^'"]+)['"]''')
_IMPORT_RE["ts"] = re.compile(r'''(?:import|from|require)\s*\(?['"](\.[^'"]+)['"]''')

_LANG_KEY: dict = {
    ".py": "py", ".js": "js", ".jsx": "js",
    ".ts": "ts", ".tsx": "ts", ".svelte": "js",
    ".kt": "kt", ".kts": "kt",
}


def _extract_imports(path: Path, ext: str) -> list:
    key = _LANG_KEY.get(ext)
    if not key:
        return []
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return [m.group(1) for m in _IMPORT_RE[key].finditer(src)]


def _resolve_import(source_file: str, imp: str, all_files: set, ext: str):
    if imp.startswith("."):
        base = Path(source_file).parent
        candidate = (base / imp).as_posix().lstrip("/")
        for try_ext in (ext, ".ts", ".tsx", ".js", ".jsx", ".svelte"):
            if candidate + try_ext in all_files:
                return candidate + try_ext
            if candidate in all_files:
                return candidate
        for idx in ("/index.ts", "/index.js"):
            if candidate + idx in all_files:
                return candidate + idx
        return None
    else:
        for f in all_files:
            stem = f.replace(ext, "").replace("/", ".")
            if stem == imp or stem.endswith("." + imp):
                return f
        return None


def build_code_graph(repo_path: Path, all_files: set):
    if not _NX_AVAILABLE:
        return None
    G = nx.DiGraph()
    G.add_nodes_from(all_files)
    for rel in all_files:
        path = repo_path / rel
        ext = Path(rel).suffix
        for imp in _extract_imports(path, ext):
            resolved = _resolve_import(rel, imp, all_files, ext)
            if resolved and resolved != rel:
                G.add_edge(rel, resolved, type="import")
    return G


def compute_code_metadata(G) -> dict:
    if not _NX_AVAILABLE or G is None or len(G) == 0:
        return {}
    in_c = nx.in_degree_centrality(G)
    out_c = nx.out_degree_centrality(G)
    centrality = {n: round((in_c.get(n, 0) + out_c.get(n, 0)) / 2, 4) for n in G.nodes}
    undirected = G.to_undirected()
    communities: dict = {}
    try:
        from networkx.algorithms.community import louvain_communities
        for i, comm in enumerate(louvain_communities(undirected, seed=42)):
            for node in comm:
                communities[node] = i
    except Exception:
        for i, comp in enumerate(nx.connected_components(undirected)):
            for node in comp:
                communities[node] = i
    return {
        node: {
            "centrality": centrality.get(node, 0.0),
            "community_id": communities.get(node, 0),
            "imports": [v for _, v in G.out_edges(node)],
            "imported_by": [u for u, _ in G.in_edges(node)],
        }
        for node in G.nodes
    }


def persist_code_graph(G, metadata: dict, repo_name: str) -> None:
    if not _NX_AVAILABLE or G is None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [{"id": n, **metadata.get(n, {})} for n in G.nodes],
        "edges": [{"source": u, "target": v, "type": d.get("type", "import")} for u, v, d in G.edges(data=True)],
    }
    out = DATA_DIR / f"graph_{repo_name}.json"
    out.write_text(json.dumps(data))
    print(f"  graph: {len(data['nodes'])} nodes, {len(data['edges'])} edges -> {out.name}")


# ---------------------------------------------------------------------------
# Notes graph (Obsidian wikilinks + PPR)
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r'\[\[([^\[\]|#]+?)(?:\|[^\[\]]+)?\]\]')


def build_notes_graph(notes_dir: Path):
    if not _NX_AVAILABLE:
        return None
    G = nx.DiGraph()
    md_files = [
        p for p in notes_dir.rglob("*.md")
        if ".obsidian" not in p.parts and ".git" not in p.parts
    ]
    stem_to_rel: dict = {}
    for path in md_files:
        rel = str(path.relative_to(notes_dir))
        G.add_node(rel)
        stem_to_rel[path.stem.lower()] = rel
    for path in md_files:
        rel = str(path.relative_to(notes_dir))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in _WIKILINK_RE.finditer(text):
            target_stem = m.group(1).lower().split("/")[-1].split(".")[0]
            target_rel = stem_to_rel.get(target_stem)
            if target_rel and target_rel != rel:
                G.add_edge(rel, target_rel, type="wikilink")
    return G


def persist_notes_graph(G) -> None:
    if not _NX_AVAILABLE or G is None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [{"id": n, "centrality": 0, "community_id": 0} for n in G.nodes],
        "edges": [{"source": u, "target": v} for u, v in G.edges],
    }
    out = DATA_DIR / "graph_notes.json"
    out.write_text(json.dumps(data))
    print(f"  notes graph: {len(data['nodes'])} nodes, {len(data['edges'])} wikilink edges -> {out.name}")


def ppr_augment(matched_files: list, scores: list, graph_path: Path, threshold: float = 0.03) -> list:
    """Personalized PageRank over wikilink graph seeded from vector-matched notes."""
    if not _NX_AVAILABLE or not graph_path.exists():
        return []
    try:
        data = json.loads(graph_path.read_text())
        G = nx.DiGraph()
        G.add_nodes_from(
            n["id"] if isinstance(n, dict) else n
            for n in data.get("nodes", [])
        )
        G.add_edges_from([(e["source"], e["target"]) for e in data.get("edges", [])])
    except Exception:
        return []
    if len(G) < 2:
        return []
    total = sum(scores) or 1.0
    personalization: dict = {n: 1e-6 for n in G.nodes}
    for f, s in zip(matched_files, scores):
        if f in personalization:
            personalization[f] += s / total
    norm = sum(personalization.values())
    personalization = {k: v / norm for k, v in personalization.items()}
    try:
        ppr = nx.pagerank(G, alpha=0.85, personalization=personalization, max_iter=100)
    except Exception:
        return []
    matched_set = set(matched_files)
    return [
        {"file": node, "ppr_score": round(score, 4)}
        for node, score in sorted(ppr.items(), key=lambda x: -x[1])
        if node not in matched_set and score >= threshold
    ][:5]
