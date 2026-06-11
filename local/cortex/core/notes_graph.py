#!/usr/bin/env python3
"""Notes graph — Obsidian wikilink edges and Personalized PageRank augmentation."""

import json
import re
from pathlib import Path

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False
    print("Warning: networkx not installed — graph features disabled")

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


def persist_notes_graph(G, data_dir: Path) -> None:
    if not _NX_AVAILABLE or G is None:
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [{"id": n, "centrality": 0, "community_id": 0} for n in G.nodes],
        "edges": [{"source": u, "target": v} for u, v in G.edges],
    }
    out = data_dir / "graph_notes.json"
    out.write_text(json.dumps(data))
    print(f"  notes graph: {len(data['nodes'])} nodes, {len(data['edges'])} wikilink edges -> {out.name}")


def ppr_augment(matched_files: list, scores: list, graph_path: Path, threshold: float = 0.03, _return_reason: bool = False):
    """Personalized PageRank over wikilink graph seeded from vector-matched notes."""
    def _ret(results, reason):
        return (results, reason) if _return_reason else results

    if not _NX_AVAILABLE or not graph_path.exists():
        return _ret([], "nx_or_missing")
    try:
        data = json.loads(graph_path.read_text())
        G = nx.DiGraph()
        G.add_nodes_from(
            n["id"] if isinstance(n, dict) else n
            for n in data.get("nodes", [])
        )
        G.add_edges_from([(e["source"], e["target"]) for e in data.get("edges", [])])
    except Exception:
        return _ret([], "exception")
    if len(G) < 2:
        return _ret([], "exception")
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
        return _ret([], "exception")
    matched_set = set(matched_files)
    results = [
        {"file": node, "ppr_score": round(score, 4)}
        for node, score in sorted(ppr.items(), key=lambda x: -x[1])
        if node not in matched_set and score >= threshold
    ][:5]
    return _ret(results, "ok" if results else "below_threshold")
