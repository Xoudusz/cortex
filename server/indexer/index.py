#!/usr/bin/env python3
"""Index Obsidian notes into Qdrant via Ollama embeddings."""

import hashlib
import os
import re
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter, FilterSelector, MatchValue,
                                  PointStruct, SparseVector, SparseVectorParams, VectorParams)

from cache import load_cache, save_cache
from chunker import _is_excluded, is_safe_file

NOTES_DIR        = Path(os.environ.get("NOTES_PATH", "/notes"))
OLLAMA_URL       = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL       = os.environ.get("QDRANT_URL", "http://qdrant:6333")
DATA_DIR         = Path(os.environ.get("REPOS_CONFIG", "/app/data/repos.json")).parent
_WS              = os.environ.get("CORTEX_WORKSPACE", "default")
COLLECTION       = "notes" if _WS == "default" else f"{_WS}_notes"
EMBED_MODEL      = "nomic-embed-text"
VECTOR_SIZE      = 768
EXCLUDE_PATTERNS = [p for p in os.environ.get("EXCLUDE_PATTERNS", "").split(",") if p]


def embed(text: str) -> list:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:MAX_CHUNK_CHARS + 300]},  # last-resort guard; chunks are pre-split
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


MAX_CHUNK_CHARS = 2500  # nomic-embed-text slot is 2048 tokens; dense text runs ~2-3 chars/token
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def _scan_fence(state, text):
    """Fence state after `text`. state = (marker, opening line) or None."""
    for ln in text.split("\n"):
        m = _FENCE.match(ln)
        if not m:
            continue
        mark, info = m.group(1), m.group(2).strip()
        if state is None:
            state = (mark, ln.strip())
        elif mark[0] == state[0][0] and len(mark) >= len(state[0]) and not info:
            state = None
    return state


def _pieces(body: str, room: int) -> list:
    """(text, joiner) pieces of body, each <= room. joiner = separator put before the piece
    when re-assembling: "\\n\\n" at paragraph start, "\\n" at line start, "" inside a hard-split line."""
    out = []
    for pi, para in enumerate(re.split(r"\n\s*\n", body)):
        para_joiner = "\n\n" if pi else ""
        if len(para) <= room:
            out.append((para, para_joiner))
            continue
        buf, buf_joiner = None, None
        for li, ln in enumerate(para.split("\n")):
            line_joiner = (para_joiner if li == 0 else "\n")
            if len(ln) > room:  # overlong line: flush buffer, hard-split the line
                if buf is not None:
                    out.append((buf, buf_joiner))
                    buf = None
                for k in range(0, len(ln), room):
                    out.append((ln[k:k + room], line_joiner if k == 0 else ""))
                continue
            if buf is None:
                buf, buf_joiner = ln, line_joiner
            elif len(buf) + 1 + len(ln) <= room:
                buf += "\n" + ln
            else:
                out.append((buf, buf_joiner))
                buf, buf_joiner = ln, "\n"
        if buf is not None:
            out.append((buf, buf_joiner))
    return out


def split_body(body: str, limit: int = MAX_CHUNK_CHARS) -> list:
    """Split a section body into parts <= limit chars at paragraph / line boundaries.
    A split inside a ``` fence closes it at the part end and reopens it in the next part."""
    if len(body) <= limit:
        return [body]
    room = limit - 200  # reserve for reopened fence line + closer
    parts, text, state = [], "", None
    for p, joiner in _pieces(body, room):
        if not text:
            text = p
            state = _scan_fence(state, p)
            continue
        after = _scan_fence(state, p)
        cand = text + joiner + p
        closer = len(after[0]) + 1 if after else 0
        if len(cand) + closer <= limit:
            text, state = cand, after
            continue
        # close the open fence (if any) and start a new part
        parts.append(text + (f"\n{state[0]}" if state else ""))
        reopen = state[1] if state and len(state[1]) <= 200 else ""  # over-long opener: not reopened
        text = (reopen + "\n" + p) if reopen else p
        state = _scan_fence(None, reopen) if reopen else None
        state = _scan_fence(state, p)
    if text:
        parts.append(text)
    return parts


def chunk_markdown(path: Path) -> list:
    raw = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(NOTES_DIR))
    modified_at = int(path.stat().st_mtime)
    text, tags = parse_frontmatter(raw)

    chunks = []

    def emit(heading, body):
        budget = max(MAX_CHUNK_CHARS - len(heading) - 22, 500)  # heading prefix + "\n\n" + "(part N)"
        parts = split_body(body, budget)
        for i, part in enumerate(parts, 1):
            h = heading if len(parts) == 1 else f"{heading} (part {i})"
            chunks.append({"heading": h, "text": f"{heading}\n\n{part}",
                           "file": rel, "tags": tags, "modified_at": modified_at})

    current_heading, current_lines = path.stem, []
    for line in text.splitlines():
        if re.match(r"^#{1,3} ", line):
            body = "\n".join(current_lines).strip()
            if body:
                emit(current_heading, body)
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        emit(current_heading, body)

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
                if ".obsidian" not in p.parts and ".git" not in p.parts and is_safe_file(p, NOTES_DIR)]

    cache = load_cache("notes")
    if client.get_collection(COLLECTION).points_count == 0:
        cache = {}
    new_cache = {}
    total = 0
    cached = 0

    for path in md_files:
        rel = str(path.relative_to(NOTES_DIR))
        if _is_excluded(rel, EXCLUDE_PATTERNS):
            continue
        mtime = path.stat().st_mtime
        entry = cache.get(rel, {})
        if entry.get("mtime") == mtime:
            new_cache[rel] = entry
            cached += 1
            continue
        content = path.read_bytes()
        content_hash = hashlib.sha1(content).hexdigest()[:16]
        if entry.get("hash") == content_hash:
            new_cache[rel] = {"mtime": mtime, "hash": content_hash}
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
        # drop previous points for this file first: split count may have changed (stale parts)
        client.delete(COLLECTION, points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="file", match=MatchValue(value=rel))])))
        if points:
            client.upsert(COLLECTION, points)
            total += len(points)
            print(f"  {rel}: {len(points)} chunk(s)", flush=True)
        new_cache[rel] = {"mtime": mtime, "hash": content_hash}

    save_cache("notes", new_cache)
    print(f"\nDone. {total} chunks indexed, {cached}/{len(md_files)} files cached (skipped).")

    # Build wikilink graph for PPR augmentation in search_notes
    try:
        import graph as _graph
        G = _graph.build_notes_graph(NOTES_DIR)
        _graph.persist_notes_graph(G, DATA_DIR)
    except Exception as e:
        print(f"  notes graph build failed: {e}")


if __name__ == "__main__":
    main()
