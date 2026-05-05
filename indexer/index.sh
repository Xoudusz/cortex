#!/usr/bin/env bash
set -e

export OLLAMA_URL="${OLLAMA_URL:-http://ollama:11434}"
export QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
export NOTES_PATH="${NOTES_PATH:-/notes}"

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Indexing notes ==="
python3 "$DIR/index.py"

echo ""
echo "=== Indexing code ==="
python3 "$DIR/index_code.py"

echo ""
echo "=== Done ==="
