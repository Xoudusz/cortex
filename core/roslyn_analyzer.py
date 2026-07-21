#!/usr/bin/env python3
"""Python wrapper for the Roslyn C# syntax analyzer subprocess."""

import json
import os
import subprocess
from pathlib import Path

ROSLYN_BINARY = Path(os.environ.get(
    "ROSLYN_ANALYZER",
    str(Path(__file__).parent / "roslyn_tool" / "CortexAnalyzer")
))


def is_available() -> bool:
    return ROSLYN_BINARY.exists() and os.access(ROSLYN_BINARY, os.X_OK)


def analyze_dir(dir_path: Path) -> dict:
    """Run Roslyn analyzer on a directory. Returns per-file symbol + type_ref data.

    Keys are relative paths (forward slashes). Returns {} on any failure.
    """
    if not is_available():
        return {}
    try:
        result = subprocess.run(
            [str(ROSLYN_BINARY), str(dir_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout)
    except Exception:
        return {}
