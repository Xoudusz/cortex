#!/usr/bin/env python3
"""Index Obsidian notes into Qdrant via Ollama embeddings."""

import hashlib
import os
import re
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, SparseVector, SparseVectorParams, VectorParams

from cache import load_cache, save_cache

NOTES_DIR   = Path(os.environ.get("NOTES_PATH", "/notes"))
OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL  = os.environ.get("QDRANT_URL", "http://qdrant:6333")
_WS         = os.environ.get("CORTEX_WORKSPACE", "default")
COLLECTION  = "notes" if _WS == "default" else f"{_WS}_notes"
EMBED_MODEL = "nomic-embed-text"
VECTOR_SIZE = 768


def embed(text: str) -> list:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


_bm25 = None


def sparse_embed(text: str) -> tuple:
    global _bm25
    if _bm25 is None:
        from fastembed import SparseTextEmbedding
        _bm25 = SparseTextEmbedding(model_name="Qdrant/bm25")
    e = list(_bm25.embed([text[:4000]]))[0]
    return e.indices.tolist(), e.values.tolist()


def parse_frontmatter(text: str) -> tuple:
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


def chunk_markdown(path: Path) -> list:
    raw = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(NOTES_DIR))
    modified_at = int(path.stat().st_mtime)
    text, tags = parse_frontmatter(raw)

    chunks, current_heading, current_lines = [], path.stem, []
    for line in text.splitlines():
        if re.match(r"^#{1,3} ", line):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chunks.append({"heading": current_heading,
                                   "text": f"{current_heading}\n\n{body}",
                                   "file": rel, "tags": tags, "modified_at": modified_at})
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chunks.append({"heading": current_heading,
                           "text": f"{current_heading}\n\n{body}",
                           "file": rel, "tags": tags, "modified_at": modified_at})

    if not chunks:
        body = text.strip()
        if body:
            chunks.append({"heading": path.stem, "text": body,
                           "file": rel, "tags": tags, "modified_at": modified_at})
    return chunks


def chunk_id(file: str, heading: str) -> int:
    return int(hashlib.md5(f"{file}:{heading}".encode()).hexdigest()[:8], 16)


def main():
    client = QdrantClient(url=QDRANT_URL)
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        print(f"Created collection '{COLLECTION}' with sparse vector support")

    sparse_available = False
    try:
        sparse_embed("warmup")
        sparse_available = True
    except Exception as e:
        print(f"  warn: sparse vectors unavailable (dense-only fallback): {e}", flush=True)

    md_files = [p for p in NOTES_DIR.rglob("*.md")
                if ".obsidian" not in p.parts and ".git" not in p.parts]

    cache = load_cache("notes")
    if client.get_collection(COLLECTION).points_count == 0:
        cache = {}
    new_cache = {}
    total = 0
    cached = 0

    for path in md_files:
        rel = str(path.relative_to(NOTES_DIR))
        mtime = path.stat().st_mtime
        if cache.get(rel) == mtime:
            new_cache[rel] = mtime
            cached += 1
            continue

        chunks = chunk_markdown(path)
        points = []
        for c in chunks:
            dense = embed(c["text"])
            if sparse_available:
                idx, vals = sparse_embed(c["text"])
                vec = {"": dense, "sparse": SparseVector(indices=idx, values=vals)}
            else:
                vec = dense
            points.append(PointStruct(
                id=chunk_id(c["file"], c["heading"]),
                vector=vec,
                payload={"file": c["file"], "heading": c["heading"], "text": c["text"],
                         "tags": c["tags"], "modified_at": c["modified_at"]},
            ))
        if points:
            client.upsert(COLLECTION, points)
            total += len(points)
            print(f"  {rel}: {len(points)} chunk(s)", flush=True)
        new_cache[rel] = mtime

    save_cache("notes", new_cache)
    print(f"\nDone. {total} chunks indexed, {cached}/{len(md_files)} files cached (skipped).")

    # Build wikilink graph for PPR augmentation in search_notes
    try:
        import graph as _graph
        G = _graph.build_notes_graph(NOTES_DIR)
        _graph.persist_notes_graph(G)
    except Exception as e:
        print(f"  notes graph build failed: {e}")


if __name__ == "__main__":
    main()
