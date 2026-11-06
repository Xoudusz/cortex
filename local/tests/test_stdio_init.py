"""End-to-end smoke test: `cortex serve` answers MCP initialize over stdio.

Catches what import tests can't: a wheel missing cortex.core, stray stdout output that
corrupts the JSON-RPC stream, and an empty serverInfo.version. Runs against the installed
`cortex` entry point with a throwaway home directory.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

VERSION = (Path(__file__).resolve().parents[2] / "VERSION").read_text().strip()
TIMEOUT = 120


def main() -> int:
    exe = shutil.which("cortex")
    if not exe:
        print("FAIL cortex entry point not on PATH")
        return 1
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, HOME=home, USERPROFILE=home, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen([exe, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env)
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout], daemon=True).start()
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "cortex-ci", "version": "0"}}}
        proc.stdin.write((json.dumps(req) + "\n").encode())
        proc.stdin.flush()
        try:
            raw = lines.get(timeout=TIMEOUT)
        except queue.Empty:
            proc.kill()
            print(f"FAIL no response within {TIMEOUT}s\nstderr:\n{proc.stderr.read().decode(errors='replace')}")
            return 1
        finally:
            if proc.poll() is None:
                proc.stdin.close()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        try:
            resp = json.loads(raw)
        except ValueError:
            print(f"FAIL first stdout line is not JSON-RPC: {raw[:200]!r}")
            return 1
        info = resp.get("result", {}).get("serverInfo", {})
        if info.get("name") != "cortex" or info.get("version") != VERSION:
            print(f"FAIL serverInfo={info} expected version {VERSION}")
            return 1
        log = Path(home) / ".cortex" / "workspaces" / "default" / "cortex.log"
        if not log.exists() or "starting" not in log.read_text(encoding="utf-8"):
            print(f"FAIL startup line missing from {log}")
            return 1
        print(f"ok  initialize -> serverInfo {info}; log has startup line")
        return 0


if __name__ == "__main__":
    sys.exit(main())
