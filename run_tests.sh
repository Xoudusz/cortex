#!/bin/bash
# Local test runner — mirrors CI exactly. Run before every commit.
# Venv: .venv/ (persistent, created once via: python3 -m venv .venv && .venv/bin/pip install -e local/)

set -euo pipefail
cd "$(dirname "$0")"

PYTHON=".venv/bin/python"

if [ ! -f "$PYTHON" ]; then
  echo "No .venv found. Run: python3 -m venv .venv && .venv/bin/pip install -e local/"
  exit 1
fi

echo "=== local/tests/test_imports.py ==="
$PYTHON local/tests/test_imports.py

echo ""
echo "=== tests/test_chunker.py ==="
$PYTHON tests/test_chunker.py

echo ""
echo "=== tests/test_indexer.py ==="
$PYTHON tests/test_indexer.py

echo ""
echo "=== tests/test_windows_local.py ==="
$PYTHON tests/test_windows_local.py

echo ""
echo "All tests passed."
