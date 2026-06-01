#!/usr/bin/env python3
"""Clone active GitHub repos and index source code into Qdrant 'code' collection."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, VectorParams

from chunker import chunk_file, CODE_EXTS, SKIP_DIRS, REPOS_DIR

OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL   = os.environ.get("QDRANT_URL", "http://qdrant:6333")
REPOS_CONFIG = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
COLLECTION   = "code"
EMBED_MODEL  = "nomic-embed-text"
VECTOR_SIZE  = 768

TOKEN = os.environ.get("GITHUB_TOKEN", "")

DEFAULT_REPOS = [
    "Xoudusz/weakness-dex",
    "Xoudusz/mtgdle",
    "Xoudusz/tower-of-evolon",
    "Xoudusz/tower-of-evolon-backend",
    "Xoudusz/svelte-radio",
    "Xoudusz/cortex",
    "Xoudusz/riftracoons-web",
]


def _load_repos() -> list:
    try:
        if os.path.exists(REPOS_CONFIG):
            with open(REPOS_CONFIG) as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict):
                repos = data.get("repos", [])
                if repos:
                    return repos
    except Exception as e:
        print(f"Warning: could not read repos config {REPOS_CONFIG}: {e}")
    return list(DEFAULT_REPOS)


def embed(text: str) -> list:
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
        print(f"  pulling {repo}...", flush=True)
        result = subprocess.run(
            ["git", "-C", str(dest), "pull"],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().splitlines():
            print(f"    {line}", flush=True)
        if result.returncode != 0:
            print(f"    git pull failed (rc={result.returncode}): {result.stderr.strip()}", flush=True)
    else:
        print(f"  cloning {repo} (shallow)...", flush=True)
        result = subprocess.run(
            ["git", "clone", "--depth=1", auth_url, str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, "git clone", result.stderr)
        for line in result.stdout.strip().splitlines():
            print(f"    {line}", flush=True)
    return dest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="", help="Only index this repo name (e.g. svelte-radio)")
    parser.add_argument("--files", nargs="*", default=None, help="Incremental: re-index only these relative paths")
    parser.add_argument("--remove-files", nargs="*", dest="remove_files", default=None, help="Incremental: delete these paths from Qdrant")
    args = parser.parse_args()

    all_repos = _load_repos()
    if args.repo:
        repos = [r for r in all_repos if r.split("/")[1] == args.repo]
        if not repos:
            print(f"Unknown repo: {args.repo}. Valid: {[r.split('/')[1] for r in all_repos]}")
            return
    else:
        repos = all_repos

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(url=QDRANT_URL)

    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection '{COLLECTION}'", flush=True)

    from chunker import _TS_AVAILABLE
    print(f"Chunking mode: {'tree-sitter' if _TS_AVAILABLE else 'sliding-window (fallback)'}", flush=True)

    for repo in repos:
        name = repo.split("/")[1]
        try:
            repo_path = clone_or_pull(repo)
        except subprocess.CalledProcessError as e:
            print(f"  SKIP {repo}: {e}", flush=True)
            continue

        incremental = args.files is not None or args.remove_files is not None
        if incremental:
            all_to_delete = list(set((args.files or []) + (args.remove_files or [])))
            if all_to_delete:
                print(f"  {name}: removing old chunks for {len(all_to_delete)} files", flush=True)
                for rel in all_to_delete:
                    try:
                        client.delete(
                            COLLECTION,
                            points_selector=FilterSelector(filter=Filter(must=[
                                FieldCondition(key="repo", match=MatchValue(value=name)),
                                FieldCondition(key="file", match=MatchValue(value=rel)),
                            ]))
                        )
                    except Exception as e:
                        print(f"  warn: delete {rel}: {e}", flush=True)
            code_files = [
                repo_path / f for f in (args.files or [])
                if (repo_path / f).exists() and Path(f).suffix in CODE_EXTS
                and not any(s in Path(f).parts for s in SKIP_DIRS)
            ]
            print(f"  {name}: incremental — {len(code_files)} files to re-index, {len(args.remove_files or [])} removed", flush=True)
        else:
            code_files = [
                p for p in repo_path.rglob("*")
                if p.is_file() and p.suffix in CODE_EXTS
                and not any(s in p.parts for s in SKIP_DIRS)
            ]

        total = 0
        file_point_ids: dict = {}

        for i, path in enumerate(code_files):
            if i % 10 == 0 and i > 0:
                print(f"  {name}: {i}/{len(code_files)} files, {total} chunks so far...", flush=True)
            points = []
            for chunk in chunk_file(path, name):
                cid = int(hashlib.md5(
                    f"{chunk['repo']}:{chunk['file']}:{chunk['start_line']}".encode()
                ).hexdigest()[:8], 16)
                points.append(PointStruct(id=cid, vector=embed(chunk["text"]), payload=chunk))
                file_point_ids.setdefault(chunk["file"], []).append(cid)
            if points:
                client.upsert(COLLECTION, points)
                total += len(points)

        print(f"  {name}: {total} chunks from {len(code_files)} files", flush=True)

        try:
            import graph as _graph
            if incremental:
                # Build from all repo files so the persisted graph stays complete.
                # file_point_ids only has changed files; using it would clobber graph_{name}.json.
                graph_files = set(
                    str(p.relative_to(repo_path))
                    for p in repo_path.rglob("*")
                    if p.is_file() and p.suffix in CODE_EXTS
                    and not any(s in p.parts for s in SKIP_DIRS)
                )
            else:
                graph_files = set(file_point_ids.keys())
            G = _graph.build_code_graph(repo_path, graph_files)
            if G is not None:
                metadata = _graph.compute_code_metadata(G)
                _graph.persist_code_graph(G, metadata, name)
                for file_rel, meta in metadata.items():
                    point_ids = file_point_ids.get(file_rel, [])
                    if point_ids:
                        client.set_payload(
                            collection_name=COLLECTION,
                            payload={
                                "centrality": meta["centrality"],
                                "community_id": meta["community_id"],
                                "imports": meta["imports"],
                                "imported_by": meta["imported_by"],
                            },
                            points=point_ids,
                        )
        except Exception as e:
            print(f"  graph build failed for {name}: {e}", flush=True)

    print("\nDone.", flush=True)

    if not args.repo:
        try:
            import graph as _graph
            repo_paths_map = {
                r.split("/")[1]: REPOS_DIR / r.split("/")[1]
                for r in repos
                if (REPOS_DIR / r.split("/")[1]).exists()
            }
            _graph.build_global_graph(repo_paths_map)
        except Exception as e:
            print(f"  global graph build failed: {e}", flush=True)


if __name__ == "__main__":
    main()
