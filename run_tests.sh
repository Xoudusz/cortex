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
echo "=== tests/test_server_indexer.py ==="
$PYTHON tests/test_server_indexer.py

echo ""
echo "=== tests/test_ignores.py ==="
$PYTHON tests/test_ignores.py

echo ""
echo "=== tests/test_users.py ==="
$PYTHON tests/test_users.py

echo ""
echo "=== tests/test_multiuser.py ==="
$PYTHON tests/test_multiuser.py

echo ""
echo "=== tests/test_godot.py ==="
$PYTHON tests/test_godot.py

echo ""
echo "=== tests/test_incremental.py (real embeddings) ==="
$PYTHON tests/test_incremental.py

echo ""
echo "All tests passed."
