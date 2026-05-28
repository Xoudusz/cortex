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
from qdrant_client.models import Distance, PointStruct, VectorParams

REPOS_DIR      = Path(os.environ.get("REPOS_DIR", "/tmp/repos"))
OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL     = os.environ.get("QDRANT_URL", "http://qdrant:6333")
REPOS_CONFIG   = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
COLLECTION     = "code"
EMBED_MODEL    = "nomic-embed-text"
VECTOR_SIZE    = 768
CHUNK_LINES    = 30
OVERLAP_LINES  = 5
MAX_CHUNK_LINES = 80

TOKEN = os.environ.get("GITHUB_TOKEN", "")

CODE_EXTS = {".js", ".ts", ".tsx", ".jsx", ".svelte", ".py", ".java", ".go", ".rs", ".css", ".html", ".kt", ".kts", ".gd", ".yml", ".yaml"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".svelte-kit", "__pycache__", ".gradle", "target"}
LANG_MAP  = {
    ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".svelte": "svelte", ".py": "python",
    ".java": "java", ".go": "go", ".rs": "rust", ".css": "css", ".html": "html",
    ".kt": "kotlin", ".kts": "kotlin", ".gd": "gdscript",
    ".yml": "yaml", ".yaml": "yaml",
}

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


try:
    from tree_sitter import Language, Parser as _TSParser
    import tree_sitter_python as _tspy
    import tree_sitter_javascript as _tsjs
    import tree_sitter_typescript as _tsts
    import tree_sitter_kotlin as _tskotlin

    _TS_LANGUAGES: dict = {
        ".py":  Language(_tspy.language()),
        ".js":  Language(_tsjs.language()),
        ".jsx": Language(_tsjs.language()),
        ".ts":  Language(_tsts.language_typescript()),
        ".tsx": Language(_tsts.language_tsx()),
        ".kt":  Language(_tskotlin.language()),
        ".kts": Language(_tskotlin.language()),
    }
    _TS_SEMANTIC: dict = {
        ".py":  {"function_definition", "class_definition"},
        ".js":  {"function_declaration", "class_declaration", "method_definition"},
        ".jsx": {"function_declaration", "class_declaration", "method_definition"},
        ".ts":  {"function_declaration", "class_declaration", "method_definition", "interface_declaration"},
        ".tsx": {"function_declaration", "class_declaration", "method_definition", "interface_declaration"},
        ".kt":  {"function_declaration", "class_declaration", "object_declaration"},
        ".kts": {"function_declaration", "class_declaration", "object_declaration"},
    }
    _TS_AVAILABLE = True
except Exception:
    _TS_AVAILABLE = False
    _TS_LANGUAGES = {}
    _TS_SEMANTIC = {}


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
        print(f"  pulling {repo}...")
        subprocess.run(["git", "-C", str(dest), "pull", "--quiet"], check=False)
    else:
        print(f"  cloning {repo}...")
        subprocess.run(["git", "clone", "--quiet", auth_url, str(dest)], check=True)
    return dest


def _sliding_window(lines: list, start: int, end: int, repo_name: str, rel: str, language: str) -> list:
    step = CHUNK_LINES - OVERLAP_LINES
    chunks = []
    i = start
    while i < end:
        j = min(i + CHUNK_LINES, end)
        body = "\n".join(lines[i:j]).strip()
        if body:
            chunks.append({
                "repo": repo_name, "file": rel, "language": language,
                "start_line": i + 1, "end_line": j,
                "text": f"# {repo_name}/{rel} (lines {i+1}-{j})\n\n{body}",
                "github_url": f"https://github.com/Xoudusz/{repo_name}/blob/master/{rel}#L{i+1}-L{j}",
            })
        if j == end:
            break
        i += step
    return chunks


def _collect_semantic_nodes(node, target_types: set, depth: int = 0, max_depth: int = 5) -> list:
    if node.type in target_types:
        return [node]
    if depth >= max_depth:
        return []
    result = []
    for child in node.children:
        result.extend(_collect_semantic_nodes(child, target_types, depth + 1, max_depth))
    return result


def chunk_file(path: Path, repo_name: str) -> list:
    try:
        source = path.read_bytes()
        lines  = source.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if not lines:
        return []

    ext      = path.suffix
    rel      = str(path.relative_to(REPOS_DIR / repo_name))
    language = LANG_MAP.get(ext, ext.lstrip("."))

    if _TS_AVAILABLE and ext in _TS_LANGUAGES:
        try:
            parser = _TSParser(_TS_LANGUAGES[ext])
            tree   = parser.parse(source)
            nodes  = _collect_semantic_nodes(tree.root_node, _TS_SEMANTIC[ext])
            if nodes:
                chunks = []
                for node in nodes:
                    s = node.start_point[0]
                    e = node.end_point[0] + 1
                    if e - s > MAX_CHUNK_LINES:
                        chunks.extend(_sliding_window(lines, s, e, repo_name, rel, language))
                    else:
                        body = "\n".join(lines[s:e]).strip()
                        if body:
                            chunks.append({
                                "repo": repo_name, "file": rel, "language": language,
                                "start_line": s + 1, "end_line": e,
                                "text": f"# {repo_name}/{rel} (lines {s+1}-{e})\n\n{body}",
                                "github_url": f"https://github.com/Xoudusz/{repo_name}/blob/master/{rel}#L{s+1}-L{e}",
                            })
                return chunks
        except Exception:
            pass

    return _sliding_window(lines, 0, len(lines), repo_name, rel, language)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="", help="Only index this repo name (e.g. svelte-radio)")
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
        print(f"Created collection '{COLLECTION}'")

    print(f"Chunking mode: {'tree-sitter' if _TS_AVAILABLE else 'sliding-window (fallback)'}")

    for repo in repos:
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
        file_point_ids: dict = {}

        for path in code_files:
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

        print(f"  {name}: {total} chunks from {len(code_files)} files")

        # Build graph and back-fill centrality/community into Qdrant payloads
        try:
            import graph as _graph
            G = _graph.build_code_graph(repo_path, set(file_point_ids.keys()))
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
            print(f"  graph build failed for {name}: {e}")

    print("\nDone.")

    # Build global cross-repo graph (only when indexing all repos)
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
            print(f"  global graph build failed: {e}")


if __name__ == "__main__":
    main()
