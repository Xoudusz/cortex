#!/usr/bin/env python3
"""Clone active GitHub repos and index source code into Qdrant 'code' collection."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, SparseVector, SparseVectorParams, VectorParams

from chunker import chunk_file, CODE_EXTS, SKIP_DIRS, REPOS_DIR, _is_excluded, repo_ignore_patterns, is_safe_file
from cache import load_cache, save_cache
import roslyn_analyzer

OLLAMA_URL       = os.environ.get("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL   = os.environ.get("QDRANT_URL", "http://qdrant:6333")
REPOS_CONFIG = os.environ.get("REPOS_CONFIG", "/app/data/repos.json")
DATA_DIR     = Path(REPOS_CONFIG).parent
_WS          = os.environ.get("CORTEX_WORKSPACE", "default")
COLLECTION       = "code" if _WS == "default" else f"{_WS}_code"
EMBED_MODEL      = "nomic-embed-text"
VECTOR_SIZE      = 768
EXCLUDE_PATTERNS = [p for p in os.environ.get("EXCLUDE_PATTERNS", "").split(",") if p]

TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Per-workspace GitHub token override from /app/data/workspace_configs.json
if _WS != "default":
    try:
        import json as _json
        _ws_cfg_path = Path(os.environ.get("DATA_DIR", "/app/data")).parent / "workspace_configs.json"
        if _ws_cfg_path.exists():
            _ws_cfg = _json.loads(_ws_cfg_path.read_text()).get(_WS, {})
            TOKEN = _ws_cfg.get("github_token", TOKEN)
    except Exception:
        pass

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


_bm25 = None


def sparse_embed(text: str) -> tuple:
    global _bm25
    if _bm25 is None:
        from fastembed import SparseTextEmbedding
        _bm25 = SparseTextEmbedding(model_name="Qdrant/bm25")
    e = list(_bm25.embed([text[:4000]]))[0]
    return e.indices.tolist(), e.values.tolist()


def _mask(text: str) -> str:
    return text.replace(TOKEN, "***") if TOKEN else text


def git_error(stderr: str) -> str:
    """Last meaningful git stderr lines (token masked) plus a hint for the common causes."""
    lines = [l.strip() for l in _mask(stderr or "").splitlines()
             if l.strip() and not l.strip().startswith("Cloning into")]
    msg = " | ".join(lines[-3:]) or "git printed no error"
    low = msg.lower()
    if "authentication failed" in low or "could not read username" in low or "403" in low:
        msg += " (hint: GitHub token missing/expired or lacks access to this repo)"
    elif "repository not found" in low or "not found" in low:
        msg += (" (hint: wrong owner/name, or the token can't see it - collaborator repos need a"
                " classic PAT with repo scope)")
    elif "could not resolve host" in low or "timed out" in low:
        msg += " (hint: network/DNS problem)"
    return msg


def _delete_file_points(client, repo_name: str, rel: str) -> None:
    try:
        client.delete(COLLECTION, points_selector=FilterSelector(filter=Filter(must=[
            FieldCondition(key="repo", match=MatchValue(value=repo_name)),
            FieldCondition(key="file", match=MatchValue(value=rel)),
        ])))
    except Exception as e:
        print(f"  warn: delete {rel}: {e}", flush=True)


_REPO_SEG_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*")
_GH_URL_RE = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?github\.com[:/]([^/\s:@]+)/([^/\s]+?)(?:\.git)?/?$")


class CloneCheckError(RuntimeError):
    """Existing clone could not be verified (git failed); the path is kept, never deleted."""


def _clone_dest(repo: str) -> Path:
    """Clone location under @owners/<owner>/<name>. '@' is not valid in GitHub names, so this never overlaps a legacy REPOS_DIR/<name> clone."""
    parts = repo.split("/")
    if len(parts) != 2 or not all(_REPO_SEG_RE.fullmatch(p) for p in parts):
        raise ValueError(f"invalid repo name: {repo!r}")
    owner, name = parts
    return REPOS_DIR / "@owners" / owner / name


def _is_own_clone(dest: Path) -> bool:
    """True only if dest is a real git clone whose own top level is dest (not a parent repo or symlink)."""
    if dest.is_symlink() or not dest.is_dir():
        return False
    git_dir = dest / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        return False
    result = subprocess.run(
        ["git", "-c", "safe.bareRepository=explicit", "-C", str(dest), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise CloneCheckError(f"cannot verify existing clone {dest.name}: git rev-parse rc={result.returncode}: {git_error(result.stderr)}")
    return Path(result.stdout.strip()).resolve() == dest.resolve()


def clone_or_pull(repo: str) -> Path:
    name = repo.split("/")[1]
    dest = _clone_dest(repo)
    dest.parent.mkdir(parents=True, exist_ok=True)
    auth_url = f"https://Xoudusz:{TOKEN}@github.com/{repo}.git"
    if dest.is_symlink() or dest.exists():
        if _is_own_clone(dest):
            print(f"  pulling {repo}...", flush=True)
            # The clone stored the token that was current then; refresh it so a rotated PAT works.
            subprocess.run(["git", "-c", "safe.bareRepository=explicit", "-C", str(dest), "remote", "set-url", "origin", auth_url],
                           capture_output=True, text=True)
            result = subprocess.run(
                ["git", "-c", "safe.bareRepository=explicit", "-C", str(dest), "pull"],
                capture_output=True, text=True,
            )
            for line in result.stdout.strip().splitlines():
                print(f"    {line}", flush=True)
            if result.returncode != 0:
                print(f"    git pull failed (rc={result.returncode}): {git_error(result.stderr)}", flush=True)
            return dest
        print(f"  replacing {repo}: {dest} is not its own git clone", flush=True)
        if dest.is_symlink() or not dest.is_dir():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    print(f"  cloning {repo} (shallow)...", flush=True)
    result = subprocess.run(
        ["git", "-c", "safe.bareRepository=explicit", "clone", "--depth=1", auth_url, str(dest)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "git clone", result.stderr)
    for line in result.stdout.strip().splitlines():
        print(f"    {line}", flush=True)
    return dest


def _origin_url(config_text: str) -> str:
    """url under [remote "origin"] in a git config file ('' if none). Plain text parse, no git call."""
    in_origin = False
    for raw in config_text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_origin = line == '[remote "origin"]'
            continue
        key, sep, value = line.partition("=")
        if in_origin and sep and key.strip().lower() == "url":
            return value.strip()
    return ""


def _is_clone_dir(path: Path) -> bool:
    """Real directory with a real .git directory (no symlinks, no git call)."""
    git_dir = path / ".git"
    return path.is_dir() and not path.is_symlink() and git_dir.is_dir() and not git_dir.is_symlink()


def _migrate_clone(path: Path, label: str) -> None:
    """Move a clone to @owners by its origin URL, or remove it. Reads .git/config only; never prints the URL."""
    try:
        config_text = (path / ".git" / "config").read_text(errors="replace")
    except OSError:
        config_text = ""
    url = _origin_url(config_text)
    match = _GH_URL_RE.match(url) if url else None
    target, slug, reason = None, "", ""
    if not match:
        reason = "no github origin"
    else:
        slug = f"{match.group(1)}/{match.group(2)}"
        try:
            target = _clone_dest(slug)
        except ValueError:
            reason = "invalid owner/name"
    if target is not None and (target.is_symlink() or target.exists()):
        reason = "target exists"
    if reason:
        shutil.rmtree(path)
        print(f"  removed legacy clone {label} ({reason})", flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(path, target)
    print(f"  migrated {label} -> {slug}", flush=True)


def _migrate_entry(child: Path) -> None:
    if child.name == "@owners" or not _REPO_SEG_RE.fullmatch(child.name):
        return  # not ours to touch
    if child.is_symlink():
        child.unlink()
        print(f"  removed legacy symlink {child.name}", flush=True)
        return
    if not child.is_dir():
        child.unlink()
        print(f"  removed legacy file {child.name}", flush=True)
        return
    if _is_clone_dir(child):
        _migrate_clone(child, child.name)
        return
    # v3.2.0 owner layout: REPOS_DIR/<owner>/<name>/.git
    for sub in sorted(child.iterdir()):
        if _REPO_SEG_RE.fullmatch(sub.name) and _is_clone_dir(sub):
            try:
                _migrate_clone(sub, f"{child.name}/{sub.name}")
            except OSError as e:
                print(f"  warn: legacy clone {child.name}/{sub.name} left in place: {e.strerror or type(e).__name__}", flush=True)
    if any(_is_clone_dir(s) for s in child.iterdir()):
        print(f"  kept legacy dir {child.name}: a clone inside could not be migrated", flush=True)
        return
    shutil.rmtree(child)
    print(f"  removed legacy dir {child.name} (no git clone inside)", flush=True)


def _migrate_legacy_clones() -> None:
    """Move or delete pre-@owners clones (REPOS_DIR/<name> and REPOS_DIR/<owner>/<name>). Never runs git; never follows symlinks."""
    if not REPOS_DIR.is_dir():
        return
    try:
        entries = sorted(REPOS_DIR.iterdir())
    except OSError as e:
        print(f"  warn: cannot list {REPOS_DIR}: {e.strerror or type(e).__name__}", flush=True)
        return
    for child in entries:
        try:
            _migrate_entry(child)
        except OSError as e:
            print(f"  warn: legacy entry {child.name} left in place: {e.strerror or type(e).__name__}", flush=True)


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
    _migrate_legacy_clones()
    client = QdrantClient(url=QDRANT_URL)

    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        print(f"Created collection '{COLLECTION}' with sparse vector support", flush=True)

    sparse_available = False
    try:
        sparse_embed("warmup")
        sparse_available = True
    except Exception as e:
        print(f"  warn: sparse vectors unavailable (dense-only fallback): {e}", flush=True)

    from chunker import _TS_AVAILABLE
    print(f"Chunking mode: {'tree-sitter' if _TS_AVAILABLE else 'sliding-window (fallback)'}", flush=True)

    for repo in repos:
        name = repo.split("/")[1]
        try:
            repo_path = clone_or_pull(repo)
        except subprocess.CalledProcessError as e:
            print(f"  SKIP {repo}: git clone failed (rc={e.returncode}): {git_error(e.output or e.stderr)}", flush=True)
            continue
        except CloneCheckError as e:
            # never auto-deleted: a damaged clone stays until someone removes it by hand
            print(f"  SKIP {repo}: {e} (if the clone is damaged, delete {_clone_dest(repo)} to re-clone)", flush=True)
            continue
        except (ValueError, OSError) as e:
            print(f"  SKIP {repo}: {e.strerror or e}" if isinstance(e, OSError) else f"  SKIP {repo}: {e}", flush=True)
            continue

        incremental = args.files is not None or args.remove_files is not None
        excludes = EXCLUDE_PATTERNS + repo_ignore_patterns(repo_path)
        if len(excludes) > len(EXCLUDE_PATTERNS):
            print(f"  {name}: {len(excludes) - len(EXCLUDE_PATTERNS)} exclude pattern(s) from .cortexignore/.gdignore", flush=True)
        if not incremental:
            file_cache = load_cache("code")
            if client.get_collection(COLLECTION).points_count == 0:
                file_cache = {}
            new_file_cache = dict(file_cache)
            cached_files = 0
        else:
            file_cache = {}
            new_file_cache = load_cache("code")
            cached_files = 0

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
                for rel in args.remove_files or []:
                    new_file_cache.pop(f"{name}/{rel}", None)
            code_files = [
                repo_path / f for f in (args.files or [])
                if is_safe_file(repo_path / f, repo_path) and Path(f).suffix in CODE_EXTS
                and not any(s in Path(f).parts for s in SKIP_DIRS)
                and not _is_excluded(Path(f).as_posix(), excludes)
            ]
            print(f"  {name}: incremental — {len(code_files)} files to re-index, {len(args.remove_files or [])} removed", flush=True)
        else:
            code_files = [
                p for p in repo_path.rglob("*")
                if is_safe_file(p, repo_path) and p.suffix in CODE_EXTS
                and not any(s in p.parts for s in SKIP_DIRS)
                and not _is_excluded(p.relative_to(repo_path).as_posix(), excludes)
            ]

        total = 0
        file_point_ids: dict = {}

        roslyn_data: dict = {}
        if roslyn_analyzer.is_available() and any(p.suffix == ".cs" for p in code_files):
            print(f"  {name}: running Roslyn analyzer...", flush=True)
            roslyn_data = roslyn_analyzer.analyze_dir(repo_path)

        for i, path in enumerate(code_files):
            if i % 10 == 0 and i > 0:
                print(f"  {name}: {i}/{len(code_files)} files, {total} chunks so far...", flush=True)

            rel_path = str(path.relative_to(repo_path)).replace("\\", "/")

            cache_key = f"{name}/{rel_path}"
            mtime = path.stat().st_mtime
            if not incremental:
                entry = file_cache.get(cache_key, {})
                if entry.get("mtime") == mtime:
                    cached_files += 1
                    continue
                content_hash = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
                if entry.get("hash") == content_hash:
                    new_file_cache[cache_key] = {"mtime": mtime, "hash": content_hash}
                    cached_files += 1
                    continue
                # changed file: drop its old chunks (ids depend on start_line, so they'd linger)
                _delete_file_points(client, name, rel_path)
            else:
                content_hash = hashlib.sha1(path.read_bytes()).hexdigest()[:16]

            points = []
            for chunk in chunk_file(path, name, base_dir=repo_path, roslyn_data=roslyn_data.get(rel_path)):
                cid = int(hashlib.md5(
                    f"{chunk['repo']}:{chunk['file']}:{chunk['start_line']}".encode()
                ).hexdigest()[:8], 16)
                dense = embed(chunk["text"])
                if sparse_available:
                    idx, vals = sparse_embed(chunk["text"])
                    vec = {"": dense, "sparse": SparseVector(indices=idx, values=vals)}
                else:
                    vec = dense
                points.append(PointStruct(id=cid, vector=vec, payload=chunk))
                file_point_ids.setdefault(chunk["file"], []).append(cid)
            if points:
                client.upsert(COLLECTION, points)
                total += len(points)
            new_file_cache[cache_key] = {"mtime": mtime, "hash": content_hash}

        if not incremental:
            # files gone from disk or newly excluded: remove their chunks + cache entries
            prefix = f"{name}/"
            current = {f"{name}/{p.relative_to(repo_path).as_posix()}" for p in code_files}
            gone = [k for k in file_cache if k.startswith(prefix) and k not in current]
            for k in gone:
                _delete_file_points(client, name, k[len(prefix):])
                new_file_cache.pop(k, None)
            if gone:
                print(f"  {name}: removed {len(gone)} deleted/excluded file(s) from the index", flush=True)
        save_cache("code", new_file_cache)
        embedded_count = len(code_files) - cached_files
        print(f"  {name}: {total} chunks from {embedded_count} files ({cached_files} cached)", flush=True)

        # For graph build: always use full file set from repo scan, not just re-embedded files.
        # In full mode with cache hits, file_point_ids only has re-embedded files — using it
        # would persist a partial graph.
        all_code_file_paths = set(
            str(p.relative_to(repo_path)) for p in code_files
        ) if not incremental else set(
            str(p.relative_to(repo_path))
            for p in repo_path.rglob("*")
            if is_safe_file(p, repo_path) and p.suffix in CODE_EXTS
            and not any(s in p.parts for s in SKIP_DIRS)
            and not _is_excluded(p.relative_to(repo_path).as_posix(), excludes)
        )

        try:
            import graph as _graph
            G = _graph.build_code_graph(repo_path, all_code_file_paths)
            if roslyn_data:
                from code_graph import inject_roslyn_edges
                inject_roslyn_edges(G, roslyn_data, all_code_file_paths)
            if G is not None:
                metadata = _graph.compute_code_metadata(G)
                _graph.persist_code_graph(G, metadata, name, DATA_DIR)
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
                r.split("/")[1]: _clone_dest(r)
                for r in repos
                if _clone_dest(r).exists()
            }
            _graph.build_global_graph(repo_paths_map, DATA_DIR)
        except Exception as e:
            print(f"  global graph build failed: {e}", flush=True)


if __name__ == "__main__":
    main()
