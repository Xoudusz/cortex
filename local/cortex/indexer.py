"""Index notes and code from a local path into embedded Qdrant."""

import hashlib
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from tqdm import tqdm

from qdrant_client.models import (
    Distance, FieldCondition, Filter, FilterSelector,
    MatchValue, PointStruct, SparseVector, SparseVectorParams, VectorParams,
)

from . import db
from .config import data_dir, cache_file, VECTOR_SIZE, get_config, read_index_meta, write_index_meta
from .embedder import embed, sparse_embed
from .core.chunker import chunk_file, CODE_EXTS, SKIP_DIRS, _is_excluded, repo_ignore_patterns
from .core.cache import load_cache, save_cache
from .core import graph as _graph
from .core import roslyn_analyzer as _roslyn

log = logging.getLogger("cortex.indexer")


def _walk_code_files(root: Path, exclude_patterns: list) -> list[Path]:
    """Walk root pruning SKIP_DIRS at directory level — avoids descending into bin/obj/node_modules."""
    found = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            p = Path(dirpath) / fname
            if p.suffix in CODE_EXTS:
                rel = p.relative_to(root).as_posix()
                if not _is_excluded(rel, exclude_patterns):
                    found.append(p)
    return found


def _ensure_collection(client, name: str) -> bool:
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        log.info(f"Created collection '{name}'")
    return True


def _sparse_available() -> bool:
    try:
        sparse_embed("warmup")
        return True
    except Exception as e:
        log.warning(f"warn: sparse unavailable: {e}")
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
    rel = path.relative_to(notes_dir).as_posix()
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


def _point_id(*parts) -> int:
    return int(hashlib.md5(":".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def _file_filter(root: str, rel: str) -> FilterSelector:
    return FilterSelector(filter=Filter(must=[
        FieldCondition(key="root", match=MatchValue(value=root)),
        FieldCondition(key="file", match=MatchValue(value=rel)),
    ]))


def _root_filter(root: str) -> Filter:
    return Filter(must=[FieldCondition(key="root", match=MatchValue(value=root))])


def _drop_files(client, collection: str, root: str, rels) -> int:
    n = 0
    for rel in rels:
        client.delete(collection, points_selector=_file_filter(root, rel))
        n += 1
    return n


def _walk_md_files(root: Path) -> list[Path]:
    found = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ".obsidian"]
        found.extend(Path(dirpath) / f for f in files if f.endswith(".md"))
    return found


def _changed(path: Path, entry: dict) -> tuple[bool, dict]:
    """(changed?, new cache entry) — mtime first, content hash as tiebreaker."""
    mtime = path.stat().st_mtime
    if entry.get("mtime") == mtime:
        return False, entry
    content_hash = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
    new_entry = {"mtime": mtime, "hash": content_hash}
    return entry.get("hash") != content_hash, new_entry


# ── Notes ───────────────────────────────────────────────────────────────────

def index_notes(notes_dir: Path, show_progress: bool = False) -> int:
    """Index all .md files under notes_dir into 'notes'. Returns chunk count.

    Changed files have their old points deleted first; files gone from disk (or newly
    excluded) are removed from the index.
    """
    exclude_patterns = get_config()["index"]["exclude_patterns"] + repo_ignore_patterns(notes_dir)
    root = notes_dir.resolve().as_posix()
    prefix = root + "/"

    client = db.client()
    _ensure_collection(client, "notes")
    use_sparse = _sparse_available()

    md_files = [p for p in _walk_md_files(notes_dir)
                if not _is_excluded(p.relative_to(notes_dir).as_posix(), exclude_patterns)]

    cache = load_cache("notes", cache_file())
    if client.get_collection("notes").points_count == 0:
        cache = {}
    # entries of other roots are kept untouched
    new_cache: dict = {k: v for k, v in cache.items() if not k.startswith(prefix)}
    seen: set = set()
    total = cached = 0

    for path in tqdm(md_files, desc="notes", disable=not show_progress):
        rel = path.relative_to(notes_dir).as_posix()
        key = prefix + rel
        seen.add(key)
        changed, entry = _changed(path, cache.get(key, {}))
        new_cache[key] = entry
        if not changed:
            cached += 1
            continue
        client.delete("notes", points_selector=_file_filter(root, rel))
        chunks = _chunk_markdown(path, notes_dir)
        points = []
        for i, c in enumerate(chunks):
            c["root"] = root
            points.append(_make_point(c["text"], _point_id(root, rel, i, c["heading"]), c, use_sparse))
        if points:
            client.upsert("notes", points)
            total += len(points)
            if not show_progress:
                log.info(f"  {rel}: {len(points)} chunk(s)")

    gone = [k[len(prefix):] for k in cache if k.startswith(prefix) and k not in seen]
    if gone:
        _drop_files(client, "notes", root, gone)
        log.info(f"  removed {len(gone)} deleted/excluded note file(s)")

    save_cache("notes", new_cache, cache_file())
    log.info(f"Done. {total} chunks indexed, {cached}/{len(md_files)} files cached.")

    try:
        G = _graph.build_notes_graph(notes_dir)
        _graph.persist_notes_graph(G, data_dir())
    except Exception as e:
        log.warning(f"  notes graph failed: {e}")

    return total


# ── Code ────────────────────────────────────────────────────────────────────

def index_code(code_dir: Path, show_progress: bool = False) -> int:
    """Index all code files under code_dir into 'code'. Returns chunk count.

    Same incremental contract as index_notes: changed files are replaced, deleted files removed.
    """
    exclude_patterns = get_config()["index"]["exclude_patterns"] + repo_ignore_patterns(code_dir)
    repo_name = code_dir.name
    root = code_dir.resolve().as_posix()
    prefix = root + "/"

    client = db.client()
    _ensure_collection(client, "code")
    use_sparse = _sparse_available()

    code_files = _walk_code_files(code_dir, exclude_patterns)

    cache = load_cache("code", cache_file())
    if client.get_collection("code").points_count == 0:
        cache = {}
    new_cache = dict(cache)
    seen: set = set()
    total = cached = 0
    file_point_ids: dict = {}

    roslyn_data: dict = {}
    if _roslyn.is_available() and any(p.suffix == ".cs" for p in code_files):
        roslyn_data = _roslyn.analyze_dir(code_dir)

    for path in tqdm(code_files, desc=repo_name, disable=not show_progress):
        rel_path = path.relative_to(code_dir).as_posix()
        key = prefix + rel_path
        seen.add(key)
        changed, entry = _changed(path, cache.get(key, {}))
        new_cache[key] = entry
        if not changed:
            cached += 1
            continue

        client.delete("code", points_selector=_file_filter(root, rel_path))
        points = []
        for chunk in chunk_file(path, repo_name, base_dir=code_dir, roslyn_data=roslyn_data.get(rel_path)):
            chunk["root"] = root
            pid = _point_id(root, chunk["file"], chunk["start_line"], chunk["end_line"])
            points.append(_make_point(chunk["text"], pid, chunk, use_sparse))
            file_point_ids.setdefault(chunk["file"], []).append(pid)
        if points:
            client.upsert("code", points)
            total += len(points)

    gone = [k[len(prefix):] for k in cache if k.startswith(prefix) and k not in seen]
    if gone:
        _drop_files(client, "code", root, gone)
        for rel in gone:
            new_cache.pop(prefix + rel, None)
        log.info(f"  {repo_name}: removed {len(gone)} deleted/excluded file(s)")

    save_cache("code", new_cache, cache_file())
    log.info(f"  {repo_name}: {total} chunks from {len(code_files) - cached} files ({cached} cached)")

    all_files = {p.relative_to(code_dir).as_posix() for p in code_files}
    try:
        G = _graph.build_code_graph(code_dir, all_files)
        if roslyn_data:
            from .core.code_graph import inject_roslyn_edges
            inject_roslyn_edges(G, roslyn_data, all_files)
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
        log.warning(f"  graph failed: {e}")

    from .state import invalidate_graph_cache
    invalidate_graph_cache(repo_name)
    return total


# ── Entry ───────────────────────────────────────────────────────────────────

def _git_head(path: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None
    except Exception:
        return None


def _count(client, collection: str, root: str) -> int:
    try:
        return client.count(collection, count_filter=_root_filter(root), exact=True).count
    except Exception:
        return 0


def index_path(path: Path, show_progress: bool = False) -> None:
    """Index a path — .md files as notes, code files as code — and record it as an index root."""
    path = path.resolve()
    data_dir().mkdir(parents=True, exist_ok=True)

    md_files = _walk_md_files(path)
    code_files = _walk_code_files(path, [])

    if md_files:
        log.info(f"Indexing notes from {path} ({len(md_files)} .md files)...")
        index_notes(path, show_progress=show_progress)

    if code_files:
        log.info(f"Indexing code from {path} ({len(code_files)} files)...")
        index_code(path, show_progress=show_progress)

    if not md_files and not code_files:
        log.info(f"No indexable files found in {path}")
        return

    root = path.as_posix()
    client = db.client()
    meta = read_index_meta()
    meta.setdefault("roots", {})[root] = {
        "indexed_at": time.time(),
        "git_head": _git_head(path),
        "notes": _count(client, "notes", root) if md_files else 0,
        "code": _count(client, "code", root) if code_files else 0,
    }
    write_index_meta(meta)
