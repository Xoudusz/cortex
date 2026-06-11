"""Index notes and code from a local path into embedded Qdrant."""

import hashlib
import re
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, FilterSelector,
    MatchValue, PointStruct, SparseVector, SparseVectorParams, VectorParams,
)

from .config import qdrant_path, data_dir, cache_file, VECTOR_SIZE, migrate_legacy
from .embedder import embed, sparse_embed
from .core.chunker import chunk_file, CODE_EXTS, SKIP_DIRS
from .core.cache import load_cache, save_cache
from .core import graph as _graph


def _qdrant() -> QdrantClient:
    migrate_legacy()
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=qdrant_path())


def _ensure_collection(client: QdrantClient, name: str) -> bool:
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        print(f"Created collection '{name}'")
    return True


def _sparse_available() -> bool:
    try:
        sparse_embed("warmup")
        return True
    except Exception as e:
        print(f"warn: sparse unavailable: {e}")
        return False


def _make_point(text: str, pid: int, payload: dict, use_sparse: bool) -> PointStruct:
    dense = embed(text)
    if use_sparse:
        idx, vals = sparse_embed(text)
        vec = {"": dense, "sparse": SparseVector(indices=idx, values=vals)}
    else:
        vec = dense
    return PointStruct(id=pid, vector=vec, payload=payload)


# ── Notes ───────────────────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple:
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not m:
        return text, []
    fm = m.group(1)
    tags = []
    tm = re.search(r"^tags:\s*\[([^\]]+)\]", fm, re.MULTILINE)
    if tm:
        tags = [t.strip().strip("\"'") for t in tm.group(1).split(",") if t.strip()]
    else:
        tm2 = re.search(r"^tags:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)", fm, re.MULTILINE)
        if tm2:
            tags = [re.sub(r"^[ \t]*-[ \t]*", "", l).strip()
                    for l in tm2.group(1).splitlines() if l.strip()]
    return text[m.end():], tags


def _chunk_markdown(path: Path, notes_dir: Path) -> list:
    raw = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(notes_dir))
    modified_at = int(path.stat().st_mtime)
    text, tags = _parse_frontmatter(raw)

    chunks, current_heading, current_lines = [], path.stem, []
    for line in text.splitlines():
        if re.match(r"^#{1,3} ", line):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chunks.append({"heading": current_heading, "file": rel, "tags": tags,
                                   "modified_at": modified_at,
                                   "text": f"{current_heading}\n\n{body}"})
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chunks.append({"heading": current_heading, "file": rel, "tags": tags,
                           "modified_at": modified_at, "text": f"{current_heading}\n\n{body}"})
    if not chunks:
        body = text.strip()
        if body:
            chunks.append({"heading": path.stem, "file": rel, "tags": tags,
                           "modified_at": modified_at, "text": body})
    return chunks


def _chunk_id(file: str, heading: str) -> int:
    return int(hashlib.md5(f"{file}:{heading}".encode()).hexdigest()[:8], 16)


def index_notes(notes_dir: Path) -> int:
    """Index all .md files in notes_dir into the 'notes' collection. Returns chunk count."""
    client = _qdrant()
    _ensure_collection(client, "notes")
    use_sparse = _sparse_available()

    md_files = [p for p in notes_dir.rglob("*.md")
                if ".obsidian" not in p.parts and ".git" not in p.parts]

    cache = load_cache("notes", cache_file())
    if client.get_collection("notes").points_count == 0:
        cache = {}
    new_cache: dict = {}
    total = 0
    cached = 0

    for path in md_files:
        rel = str(path.relative_to(notes_dir))
        mtime = path.stat().st_mtime
        if cache.get(rel) == mtime:
            new_cache[rel] = mtime
            cached += 1
            continue
        chunks = _chunk_markdown(path, notes_dir)
        points = [_make_point(c["text"], _chunk_id(c["file"], c["heading"]), c, use_sparse)
                  for c in chunks]
        if points:
            client.upsert("notes", points)
            total += len(points)
            print(f"  {rel}: {len(points)} chunk(s)", flush=True)
        new_cache[rel] = mtime

    save_cache("notes", new_cache, cache_file())
    print(f"Done. {total} chunks indexed, {cached}/{len(md_files)} files cached.", flush=True)

    try:
        G = _graph.build_notes_graph(notes_dir)
        _graph.persist_notes_graph(G, data_dir())
    except Exception as e:
        print(f"  notes graph failed: {e}")

    return total


# ── Code ────────────────────────────────────────────────────────────────────

def _code_chunk_id(repo: str, file: str, start: int) -> int:
    return int(hashlib.md5(f"{repo}:{file}:{start}".encode()).hexdigest()[:8], 16)


def index_code(code_dir: Path) -> int:
    """Index all code files in code_dir into the 'code' collection. Returns chunk count."""
    repo_name = code_dir.name
    client = _qdrant()
    _ensure_collection(client, "code")
    use_sparse = _sparse_available()

    code_files = [
        p for p in code_dir.rglob("*")
        if p.is_file() and p.suffix in CODE_EXTS
        and not any(s in p.parts for s in SKIP_DIRS)
    ]

    cache = load_cache("code", cache_file())
    if client.get_collection("code").points_count == 0:
        cache = {}
    new_cache = dict(cache)
    total = 0
    cached = 0
    file_point_ids: dict = {}

    for i, path in enumerate(code_files):
        if i % 10 == 0 and i > 0:
            print(f"  {repo_name}: {i}/{len(code_files)} files, {total} chunks...", flush=True)

        cache_key = f"{repo_name}/{str(path.relative_to(code_dir))}"
        mtime = path.stat().st_mtime
        if cache.get(cache_key) == mtime:
            cached += 1
            continue

        points = []
        for chunk in chunk_file(path, repo_name, base_dir=code_dir):
            pid = _code_chunk_id(repo_name, chunk["file"], chunk["start_line"])
            points.append(_make_point(chunk["text"], pid, chunk, use_sparse))
            file_point_ids.setdefault(chunk["file"], []).append(pid)
        if points:
            client.upsert("code", points)
            total += len(points)
            new_cache[cache_key] = mtime

    save_cache("code", new_cache, cache_file())
    print(f"  {repo_name}: {total} chunks from {len(code_files) - cached} files ({cached} cached)", flush=True)

    all_files = {
        str(p.relative_to(code_dir)) for p in code_files
    }
    try:
        G = _graph.build_code_graph(code_dir, all_files)
        if G is not None:
            metadata = _graph.compute_code_metadata(G)
            _graph.persist_code_graph(G, metadata, repo_name, data_dir())
            for file_rel, meta in metadata.items():
                pids = file_point_ids.get(file_rel, [])
                if pids:
                    client.set_payload(
                        collection_name="code",
                        payload={
                            "centrality": meta["centrality"],
                            "community_id": meta["community_id"],
                            "imports": meta["imports"],
                            "imported_by": meta["imported_by"],
                        },
                        points=pids,
                    )
    except Exception as e:
        print(f"  graph failed: {e}")

    from .state import invalidate_graph_cache
    invalidate_graph_cache(repo_name)
    return total


def index_path(path: Path) -> None:
    """Index a path — .md files as notes, code files as code."""
    path = path.resolve()
    data_dir().mkdir(parents=True, exist_ok=True)

    md_files = list(path.rglob("*.md"))
    code_files = [p for p in path.rglob("*")
                  if p.is_file() and p.suffix in CODE_EXTS
                  and not any(s in p.parts for s in SKIP_DIRS)]

    if md_files:
        print(f"\nIndexing notes from {path} ({len(md_files)} .md files)...")
        index_notes(path)

    if code_files:
        print(f"\nIndexing code from {path} ({len(code_files)} files)...")
        index_code(path)

    if not md_files and not code_files:
        print(f"No indexable files found in {path}")
