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
# Code graph (import + call + inheritance edges)
# ---------------------------------------------------------------------------

_IMPORT_RE: dict = {
    "py": re.compile(r'^(?:from|import)\s+([\w.]+)', re.MULTILINE),
    "js": re.compile(r'''(?:import|from|require)\s*\(?['"](\.[^'"]+)['"]'''),
    "ts": re.compile(r'''(?:import|from|require)\s*\(?['"](\.[^'"]+)['"]'''),
    "kt": re.compile(r'^import\s+([\w.]+)', re.MULTILINE),
}

_NAMED_IMPORT_RE = re.compile(
    r'''import\s*\{([^}]+)\}\s*from\s*['"](\.[^'"]+)['"]'''
)
_DEFAULT_IMPORT_RE = re.compile(
    r'''import\s+(\w+)\s+from\s*['"](\.[^'"]+)['"]'''
)
_CALL_RE = re.compile(r'\b(\w+)\s*\(')

_TOP_LEVEL_DEF_RE: dict = {
    "py": re.compile(r'^(?:class|def)\s+(\w+)', re.MULTILINE),
    "ts": re.compile(r'(?:export\s+)?(?:class|function|const|interface|type)\s+(\w+)'),
    "kt": re.compile(r'(?:class|fun|object)\s+(\w+)'),
}

_INHERIT_RE: dict = {
    "py": re.compile(r'^class\s+\w+\s*\(([^)]+)\)', re.MULTILINE),
    "ts": re.compile(
        r'class\s+\w+(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?'
    ),
    "kt": re.compile(
        r'(?:class|interface|object)\s+\w+[^:{]*:\s*([\w,\s()]+?)(?:\{|$)',
        re.MULTILINE,
    ),
}

_LANG_KEY: dict = {
    ".py": "py", ".js": "js", ".jsx": "js",
    ".ts": "ts", ".tsx": "ts", ".svelte": "js",
    ".kt": "kt", ".kts": "kt",
}

_EDGE_PRIORITY: dict = {"import": 0, "call": 1, "inherits": 2}

_PY_SKIP_BASES = frozenset({
    "object", "ABC", "ABCMeta", "BaseModel", "Exception", "BaseException",
    "ValueError", "TypeError", "RuntimeError", "str", "int", "float",
    "list", "dict", "set", "tuple", "Enum", "IntEnum",
})
_TS_SKIP_BASES = frozenset({"Error", "EventEmitter", "Component", "React"})


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


def _build_symbol_map(repo_path: Path, all_files: set) -> dict:
    """Map top-level symbol names to their source file."""
    symbol_to_file: dict = {}
    for rel in all_files:
        ext = Path(rel).suffix
        key = _LANG_KEY.get(ext)
        pat = _TOP_LEVEL_DEF_RE.get(key)
        if not pat:
            continue
        try:
            src = (repo_path / rel).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in pat.finditer(src):
            name = m.group(1)
            if name not in symbol_to_file:
                symbol_to_file[name] = rel
    return symbol_to_file


def _extract_named_imports_map(src: str) -> dict:
    """Return {imported_name: relative_path} for named + default JS/TS imports."""
    result: dict = {}
    for m in _NAMED_IMPORT_RE.finditer(src):
        raw_path = m.group(2)
        for part in m.group(1).split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                result[name] = raw_path
    for m in _DEFAULT_IMPORT_RE.finditer(src):
        result[m.group(1)] = m.group(2)
    return result


def _extract_call_targets(path: Path, ext: str, all_files: set, rel: str) -> list:
    """Call edges for JS/TS: resolve imported names that are actually called."""
    if ext not in (".js", ".jsx", ".ts", ".tsx", ".svelte"):
        return []
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    named = _extract_named_imports_map(src)
    if not named:
        return []
    called = {m.group(1) for m in _CALL_RE.finditer(src)}
    targets: set = set()
    for name, imp_path in named.items():
        if name in called:
            resolved = _resolve_import(rel, imp_path, all_files, ext)
            if resolved and resolved != rel:
                targets.add(resolved)
    return list(targets)


def _extract_inheritance_targets(
    path: Path, ext: str, all_files: set, rel: str, symbol_to_file: dict
) -> list:
    """Inheritance edges: class Foo(Bar) / extends Bar / implements Bar."""
    key = _LANG_KEY.get(ext)
    if key not in _INHERIT_RE:
        return []
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    targets: set = set()
    skip = _PY_SKIP_BASES if key == "py" else _TS_SKIP_BASES

    if key == "py":
        for m in _INHERIT_RE["py"].finditer(src):
            for base in m.group(1).split(","):
                base = base.strip().split(".")[0]
                if base and base not in skip:
                    t = symbol_to_file.get(base)
                    if t and t != rel:
                        targets.add(t)

    elif key == "ts":
        for m in _INHERIT_RE["ts"].finditer(src):
            for grp in (m.group(1), m.group(2)):
                if not grp:
                    continue
                for base in grp.split(","):
                    base = base.strip().split("<")[0].strip()
                    if base and base not in skip:
                        t = symbol_to_file.get(base)
                        if t and t != rel:
                            targets.add(t)

    elif key == "kt":
        for m in _INHERIT_RE["kt"].finditer(src):
            for base in m.group(1).split(","):
                base = re.sub(r'\(.*?\)', '', base).strip()
                if base and base not in skip:
                    t = symbol_to_file.get(base)
                    if t and t != rel:
                        targets.add(t)

    return list(targets)


def _add_edge(G, src: str, dst: str, edge_type: str) -> None:
    """Add edge, upgrading type if higher-priority edge found (import < call < inherits)."""
    if G.has_edge(src, dst):
        existing = G[src][dst].get("type", "import")
        if _EDGE_PRIORITY.get(edge_type, 0) > _EDGE_PRIORITY.get(existing, 0):
            G[src][dst]["type"] = edge_type
    else:
        G.add_edge(src, dst, type=edge_type)


def build_code_graph(repo_path: Path, all_files: set):
    if not _NX_AVAILABLE:
        return None
    G = nx.DiGraph()
    G.add_nodes_from(all_files)
    symbol_to_file = _build_symbol_map(repo_path, all_files)
    for rel in all_files:
        path = repo_path / rel
        ext = Path(rel).suffix
        for imp in _extract_imports(path, ext):
            resolved = _resolve_import(rel, imp, all_files, ext)
            if resolved and resolved != rel:
                _add_edge(G, rel, resolved, "import")
        for target in _extract_call_targets(path, ext, all_files, rel):
            _add_edge(G, rel, target, "call")
        for target in _extract_inheritance_targets(path, ext, all_files, rel, symbol_to_file):
            _add_edge(G, rel, target, "inherits")
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
    edge_counts = {t: sum(1 for _, _, d in G.edges(data=True) if d.get("type") == t)
                   for t in ("import", "call", "inherits")}
    data = {
        "nodes": [{"id": n, **metadata.get(n, {})} for n in G.nodes],
        "edges": [
            {"source": u, "target": v, "type": d.get("type", "import")}
            for u, v, d in G.edges(data=True)
        ],
    }
    out = DATA_DIR / f"graph_{repo_name}.json"
    out.write_text(json.dumps(data))
    print(
        f"  graph: {len(data['nodes'])} nodes, {len(data['edges'])} edges "
        f"(import:{edge_counts['import']} call:{edge_counts['call']} "
        f"inherits:{edge_counts['inherits']}) -> {out.name}"
    )


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
