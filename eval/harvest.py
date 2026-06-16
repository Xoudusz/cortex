#!/usr/bin/env python3
"""Review real search queries from search_log.jsonl and print golden set candidates.

Usage:
    # Server mode — copy log out of container first:
    docker exec cortex-mcp cat /app/data/search_log.jsonl > /tmp/search_log.jsonl
    python3 eval/harvest.py --log /tmp/search_log.jsonl

    # Local mode (auto-detected):
    python3 eval/harvest.py

    # Filter to notes queries, require 2+ occurrences:
    python3 eval/harvest.py --tool search_notes --min-count 2

    # Write candidates to file for review:
    python3 eval/harvest.py --output eval/candidates.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_LOCAL_LOG_CANDIDATES = [
    Path.home() / ".cortex" / "workspaces" / "default" / "search_log.jsonl",
    Path.home() / ".cortex" / "search_log.jsonl",
    Path("/app/data/search_log.jsonl"),
]


def _find_log() -> Path | None:
    for p in _LOCAL_LOG_CANDIDATES:
        if p.exists():
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", help="Path to search_log.jsonl")
    parser.add_argument("--tool", default="search_code", choices=["search_code", "search_notes", "all"])
    parser.add_argument("--min-count", type=int, default=1, metavar="N", help="Only show queries seen ≥N times (default: 1)")
    parser.add_argument("--output", metavar="FILE", help="Write candidates JSON to FILE for review")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else _find_log()
    if not log_path or not log_path.exists():
        print(f"No log found. Checked:\n" + "\n".join(f"  {p}" for p in _LOCAL_LOG_CANDIDATES))
        print("\nServer: docker exec cortex-mcp cat /app/data/search_log.jsonl > /tmp/search_log.jsonl")
        sys.exit(1)

    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    if args.tool != "all":
        entries = [e for e in entries if e.get("tool") == args.tool]

    if not entries:
        print(f"No entries for tool={args.tool!r} in {log_path}")
        sys.exit(0)

    # Aggregate: count occurrences, keep first top-results seen
    counts: dict[str, int] = defaultdict(int)
    first_top: dict[str, list] = {}
    for e in entries:
        q = e.get("query", "").strip()
        if not q:
            continue
        counts[q] += 1
        if q not in first_top:
            first_top[q] = e.get("top", [])

    rows = [(q, counts[q], first_top[q]) for q in counts if counts[q] >= args.min_count]
    rows.sort(key=lambda x: -x[1])

    print(f"Log: {log_path}  ({len(entries)} entries, {len(rows)} unique queries matching filters)\n")
    print(f"{'CNT':>4}  {'TOP-1 FILE':<45}  QUERY")
    print("-" * 90)

    candidates = []
    for query, count, top in rows:
        top1 = top[0] if top else {}
        repo = top1.get("repo", "?")
        file_ = top1.get("file", "?")
        score = top1.get("score", 0)
        print(f"{count:4d}  {f'{repo}/{file_}':<45}  {query}")
        candidates.append({
            "query": query,
            "expected_files": [file_],
            "repo": repo,
            "_count": count,
            "_score": score,
            "_top3": [
                {"repo": t.get("repo", ""), "file": t.get("file", ""), "score": t.get("score", 0)}
                for t in top[:3]
            ],
        })

    print()
    print("NOTE: 'expected_files' = top-1 result (assumed correct). Verify before adding to golden.json.")
    print("Remove _count, _score, _top3 fields when adding entries to golden.json.")

    if args.output:
        Path(args.output).write_text(json.dumps(candidates, indent=2))
        print(f"\nWrote {len(candidates)} candidates → {args.output}")


if __name__ == "__main__":
    main()
