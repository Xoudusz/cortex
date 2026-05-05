#!/usr/bin/env python3
"""Index Obsidian notes into Qdrant via Ollama embeddings."""

import hashlib
import os
import re
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

NOTES_DIR   = Path(os.environ.get("NOTES_PATH", "/notes"))
OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL  = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION  = "notes"
EMBED_MODEL = "nomic-embed-text"
VECTOR_SIZE = 768


def embed(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def parse_frontmatter(text: str) -> tuple[str, list[str]]:
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


def chunk_markdown(path: Path) -> list[dict]:
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
        client.create_collection(COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))
        print(f"Created collection '{COLLECTION}'")

    md_files = [p for p in NOTES_DIR.rglob("*.md")
                if ".obsidian" not in p.parts and ".git" not in p.parts]

    total = 0
    for path in md_files:
        chunks = chunk_markdown(path)
        points = [
            PointStruct(
                id=chunk_id(c["file"], c["heading"]),
                vector=embed(c["text"]),
                payload={"file": c["file"], "heading": c["heading"], "text": c["text"],
                         "tags": c["tags"], "modified_at": c["modified_at"]},
            )
            for c in chunks
        ]
        if points:
            client.upsert(COLLECTION, points)
            total += len(points)
            print(f"  {path.relative_to(NOTES_DIR)}: {len(points)} chunk(s)")

    print(f"\nDone. {total} chunks indexed into '{COLLECTION}'.")


if __name__ == "__main__":
    main()
