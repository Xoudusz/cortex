#!/usr/bin/env python3
"""Clone active GitHub repos and index source code into Qdrant 'code' collection."""

import hashlib
import os
import subprocess
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

REPOS_DIR   = Path(os.environ.get("REPOS_DIR", "/tmp/repos"))
OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL  = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION  = "code"
EMBED_MODEL = "nomic-embed-text"
VECTOR_SIZE = 768
CHUNK_LINES = 30
OVERLAP_LINES = 5

TOKEN = os.environ.get("GITHUB_TOKEN", "")

CODE_EXTS = {".js", ".ts", ".tsx", ".jsx", ".svelte", ".py", ".java", ".go", ".rs", ".css", ".html", ".kt", ".kts", ".gd"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".svelte-kit", "__pycache__", ".gradle", "target"}
LANG_MAP  = {
    ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".svelte": "svelte", ".py": "python",
    ".java": "java", ".go": "go", ".rs": "rust", ".css": "css", ".html": "html",
    ".kt": "kotlin", ".kts": "kotlin", ".gd": "gdscript",
}

REPOS = [
    "Xoudusz/weakness-dex",
    "Xoudusz/mtgdle",
    "Xoudusz/tower-of-evolon",
    "Xoudusz/tower-of-evolon-backend",
    "Xoudusz/svelte-radio",
]


def embed(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text[:4000]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def clone_or_pull(repo: str) -> Path:
    name = repo.split("/")[1]
    dest = REPOS_DIR / name
    auth_url = f"https://Xoudusz:{TOKEN}@github.com/{repo}.git"
    if dest.exists():
        print(f"  pulling {repo}...")
        subprocess.run(["git", "-C", str(dest), "pull", "--quiet"], check=False)
    else:
        print(f"  cloning {repo}...")
        subprocess.run(["git", "clone", "--quiet", auth_url, str(dest)], check=True)
    return dest


def chunk_file(path: Path, repo_name: str) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if not lines:
        return []

    rel      = str(path.relative_to(REPOS_DIR / repo_name))
    language = LANG_MAP.get(path.suffix, path.suffix.lstrip("."))
    chunks, step = [], CHUNK_LINES - OVERLAP_LINES

    for start in range(0, len(lines), step):
        end  = min(start + CHUNK_LINES, len(lines))
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        chunks.append({
            "repo": repo_name, "file": rel, "language": language,
            "start_line": start + 1, "end_line": end,
            "text": f"# {repo_name}/{rel} (lines {start+1}-{end})\n\n{body}",
            "github_url": f"https://github.com/Xoudusz/{repo_name}/blob/master/{rel}#L{start+1}-L{end}",
        })
        if end == len(lines):
            break
    return chunks


def main():
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(url=QDRANT_URL)

    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))
        print(f"Created collection '{COLLECTION}'")

    for repo in REPOS:
        name = repo.split("/")[1]
        try:
            repo_path = clone_or_pull(repo)
        except subprocess.CalledProcessError as e:
            print(f"  SKIP {repo}: {e}")
            continue

        code_files = [
            p for p in repo_path.rglob("*")
            if p.is_file() and p.suffix in CODE_EXTS
            and not any(s in p.parts for s in SKIP_DIRS)
        ]

        total = 0
        for path in code_files:
            points = []
            for chunk in chunk_file(path, name):
                cid = int(hashlib.md5(
                    f"{chunk['repo']}:{chunk['file']}:{chunk['start_line']}".encode()
                ).hexdigest()[:8], 16)
                points.append(PointStruct(id=cid, vector=embed(chunk["text"]), payload=chunk))
            if points:
                client.upsert(COLLECTION, points)
                total += len(points)

        print(f"  {name}: {total} chunks from {len(code_files)} files")

    print("\nDone.")


if __name__ == "__main__":
    main()
