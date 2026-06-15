#!/usr/bin/env python3
"""Cortex search quality eval — hit@1/3/5 + MRR against golden query set.

Usage:
  python eval/run.py                        # direct Qdrant (default)
  python eval/run.py --save baseline        # save as named baseline
  python eval/run.py --compare baseline     # compare against saved baseline
  python eval/run.py --url http://... --token <tok>  # via cortex HTTP API
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).parent
GOLDEN_FILE = EVAL_DIR / "golden.json"
BASELINES_FILE = EVAL_DIR / "baselines.json"

DEFAULT_QDRANT = "http://192.168.68.103:6333"
DEFAULT_LIMIT = 5


def _ollama_embed(text: str, ollama_url: str) -> list:
    import urllib.request
    payload = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["embedding"]


def _search_qdrant(qdrant_url: str, ollama_url: str = "http://192.168.68.103:11434"):
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue, Prefetch, Fusion, SparseVector

    client = QdrantClient(url=qdrant_url)

    try:
        from fastembed import SparseTextEmbedding
        _sparse = SparseTextEmbedding(model_name="Qdrant/bm25")
        def _sparse_embed(text: str):
            result = list(_sparse.embed([text]))[0]
            return result.indices.tolist(), result.values.tolist()
        _has_sparse = True
    except Exception:
        _has_sparse = False

    def search(query: str, limit: int, repo: str = "") -> list[str]:
        vector = _ollama_embed(query, ollama_url)
        fetch_limit = min(limit * 3, 50)
        q_filter = Filter(must=[FieldCondition(key="repo", match=MatchValue(value=repo))]) if repo else None

        if _has_sparse:
            try:
                idx, vals = _sparse_embed(query)
                results = client.query_points(
                    "code",
                    prefetch=[
                        Prefetch(query=vector, using=None, limit=fetch_limit),
                        Prefetch(query=SparseVector(indices=idx, values=vals), using="sparse", limit=fetch_limit),
                    ],
                    query=Fusion.RRF,
                    limit=fetch_limit,
                    with_payload=True,
                    query_filter=q_filter,
                ).points
            except Exception:
                results = client.query_points("code", query=vector, limit=fetch_limit, with_payload=True, query_filter=q_filter).points
        else:
            results = client.query_points("code", query=vector, limit=fetch_limit, with_payload=True, query_filter=q_filter).points

        # mirror production centrality re-ranking
        scored = [(r.score * (1.0 + 0.2 * r.payload.get("centrality", 0.0)), r) for r in results]
        scored.sort(key=lambda x: -x[0])

        seen: set = set()
        files = []
        for _, r in scored:
            f = r.payload.get("file", "")
            if f not in seen:
                seen.add(f)
                files.append(f)
            if len(files) >= limit:
                break
        return files

    return search


def _search_api(url: str, token: str):
    import urllib.request

    def search(query: str, limit: int, repo: str = "") -> list[str]:
        payload = json.dumps({"query": query, "collections": ["code"], "limit": limit * 3, "repo": repo}).encode()
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/search",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        seen: set = set()
        files = []
        for r in data.get("code", []):
            f = r["file"]
            if f not in seen:
                seen.add(f)
                files.append(f)
            if len(files) >= limit:
                break
        return files

    return search


def _metrics(results: list[str], expected: list[str]) -> dict:
    exp = set(expected)
    rr = next((1.0 / (i + 1) for i, f in enumerate(results) if f in exp), 0.0)
    return {
        "hit@1": any(f in exp for f in results[:1]),
        "hit@3": any(f in exp for f in results[:3]),
        "hit@5": any(f in exp for f in results[:5]),
        "rr": rr,
    }


def run_eval(golden: list, search_fn, limit: int) -> dict:
    per_query = []
    for q in golden:
        query = q["query"]
        expected = q["expected_files"]
        repo = q.get("repo", "")
        t0 = time.time()
        try:
            results = search_fn(query, limit, repo)
        except Exception as e:
            print(f"  ERROR {query!r}: {e}", file=sys.stderr)
            results = []
        elapsed = round(time.time() - t0, 2)
        m = _metrics(results, expected)
        first_hit_rank = next((i + 1 for i, f in enumerate(results) if f in set(expected)), None)
        per_query.append({
            "query": query,
            "hit@1": m["hit@1"], "hit@3": m["hit@3"], "hit@5": m["hit@5"],
            "rr": round(m["rr"], 4),
            "first_hit_rank": first_hit_rank,
            "elapsed_s": elapsed,
            "results": results,
            "expected": expected,
        })

    n = len(per_query)
    return {
        "hit@1": round(sum(q["hit@1"] for q in per_query) / n * 100, 1),
        "hit@3": round(sum(q["hit@3"] for q in per_query) / n * 100, 1),
        "hit@5": round(sum(q["hit@5"] for q in per_query) / n * 100, 1),
        "mrr": round(sum(q["rr"] for q in per_query) / n, 4),
        "n": n,
        "per_query": per_query,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def print_report(result: dict, label: str = "current", baseline: dict | None = None) -> None:
    def _diff(key: str) -> str:
        if not baseline:
            return ""
        delta = result[key] - baseline[key]
        sign = "+" if delta > 0 else ""
        return f"  ({sign}{delta:.1f})" if key != "mrr" else f"  ({sign}{delta:.4f})"

    print(f"\n=== {label} (n={result['n']}) ===")
    print(f"  hit@1  {result['hit@1']:5.1f}%{_diff('hit@1')}")
    print(f"  hit@3  {result['hit@3']:5.1f}%{_diff('hit@3')}")
    print(f"  hit@5  {result['hit@5']:5.1f}%{_diff('hit@5')}")
    print(f"  MRR    {result['mrr']:.4f}{_diff('mrr')}")
    print()
    print(f"  {'✓/✗':<4} {'query':<45} {'rank':<6} {'ms'}")
    print(f"  {'-'*4} {'-'*45} {'-'*6} {'-'*6}")
    for q in result["per_query"]:
        mark = "✓" if q["hit@5"] else "✗"
        rank = str(q["first_hit_rank"]) if q["first_hit_rank"] else "-"
        ms = int(q["elapsed_s"] * 1000)
        print(f"  {mark:<4} {q['query'][:45]:<45} {rank:<6} {ms}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qdrant", default=DEFAULT_QDRANT)
    parser.add_argument("--ollama", default="http://192.168.68.103:11434")
    parser.add_argument("--url", help="Cortex server URL (uses API instead of direct Qdrant)")
    parser.add_argument("--token", default=os.environ.get("CORTEX_TOKEN", ""))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--save", metavar="NAME", help="Save results as named baseline")
    parser.add_argument("--compare", metavar="NAME", help="Compare against named baseline")
    args = parser.parse_args()

    if not GOLDEN_FILE.exists():
        print(f"ERROR: {GOLDEN_FILE} not found. Create it with query/expected_files pairs.", file=sys.stderr)
        sys.exit(1)

    golden = json.loads(GOLDEN_FILE.read_text())
    if not golden:
        print("ERROR: golden.json is empty.", file=sys.stderr)
        sys.exit(1)

    if args.url:
        if not args.token:
            print("ERROR: --token required when using --url", file=sys.stderr)
            sys.exit(1)
        search_fn = _search_api(args.url, args.token)
        mode = f"api:{args.url}"
    else:
        search_fn = _search_qdrant(args.qdrant, args.ollama)
        mode = f"qdrant:{args.qdrant} ollama:{args.ollama}"

    print(f"Running eval: {len(golden)} queries, limit={args.limit}, mode={mode}")
    result = run_eval(golden, search_fn, args.limit)

    baseline = None
    if args.compare:
        if BASELINES_FILE.exists():
            baselines = json.loads(BASELINES_FILE.read_text())
            baseline = baselines.get(args.compare)
            if not baseline:
                print(f"WARNING: baseline '{args.compare}' not found in {BASELINES_FILE}", file=sys.stderr)
        else:
            print(f"WARNING: {BASELINES_FILE} not found", file=sys.stderr)

    print_report(result, label=args.save or "current", baseline=baseline)

    if args.save:
        baselines = {}
        if BASELINES_FILE.exists():
            baselines = json.loads(BASELINES_FILE.read_text())
        baselines[args.save] = {k: result[k] for k in ("hit@1", "hit@3", "hit@5", "mrr", "n", "timestamp")}
        BASELINES_FILE.write_text(json.dumps(baselines, indent=2))
        print(f"\nSaved baseline '{args.save}' to {BASELINES_FILE}")


import os
if __name__ == "__main__":
    main()
