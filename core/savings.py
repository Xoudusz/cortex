#!/usr/bin/env python3
"""Token-savings accounting: observed (full file - returned chunk) + modeled (50% of unreturned candidates).

Stdlib only; must not import other core modules. Tokens are estimated as bytes/4.
All stats mutation happens under LOCK; serializers must use snapshot().
"""

import copy
import json
import math
import threading
import time
from pathlib import Path

MODEL_PCT = 0.5
SESSION_TTL = 1800
LOCK = threading.RLock()

_FLAT_KEYS = (
    "tokens_observed_code", "tokens_observed_notes", "tokens_modeled_code",
    "savings_hits_measured", "savings_hits_unmeasured",
)


def file_tokens(nbytes: int) -> int:
    return math.ceil(nbytes / 4)


def text_tokens(s: str) -> int:
    return len(s) // 4


class SessionStore:
    """Per-session set of already-counted files; resets after `ttl` seconds idle (None = never)."""

    def __init__(self, ttl):
        self.ttl = ttl
        self._data: dict = {}

    def touch(self, key, now=None) -> set:
        now = time.time() if now is None else now
        with LOCK:
            if self.ttl is not None:
                for k in [k for k, (last, _) in self._data.items() if now - last > self.ttl]:
                    del self._data[k]
            entry = self._data.get(key)
            counted = entry[1] if entry else set()
            self._data[key] = (now, counted)
            return counted


SERVER_STORE = SessionStore(SESSION_TTL)


def _int_bytes(meta):
    b = meta.get("bytes") if isinstance(meta, dict) else None
    return b if isinstance(b, int) and not isinstance(b, bool) and b >= 0 else None


def _prep(stats: dict) -> None:
    for k in _FLAT_KEYS:
        if not isinstance(stats.get(k), (int, float)):
            stats[k] = 0
    for k in ("savings_by_repo", "savings_by_user"):
        if not isinstance(stats.get(k), dict):
            stats[k] = {}


def _bucket(stats: dict, group: str, name: str) -> dict:
    g = stats[group]
    b = g.get(name)
    if not isinstance(b, dict):
        b = g[name] = {}
    for k in ("observed", "modeled", "hits"):
        if not isinstance(b.get(k), (int, float)):
            b[k] = 0
    return b


def _add(stats, repo, user, observed=0, modeled=0, hits=0):
    targets = [_bucket(stats, "savings_by_repo", repo)]
    if user is not None:
        targets.append(_bucket(stats, "savings_by_user", user))
    for b in targets:
        b["observed"] += observed
        b["modeled"] += modeled
        b["hits"] += hits


def record_code(stats, store, session_key, hits, candidates, user=None, now=None):
    """hits=[(repo, file, chunk_text, meta)] returned; candidates=[(repo, file, meta)] not returned.

    Observed and modeled share one per-session dedup set on purpose: a file credited as modeled
    earlier gets no observed credit if returned later, so no file is ever counted twice.
    """
    with LOCK:
        _prep(stats)
        counted = store.touch(session_key, now)
        for repo, file, chunk_text, meta in hits:
            k = f"{repo}/{file}"
            if k in counted:
                continue
            counted.add(k)
            nbytes = _int_bytes(meta)
            if nbytes is None:
                stats["savings_hits_unmeasured"] += 1
                _add(stats, repo, user, hits=1)
                continue
            obs = max(0, file_tokens(nbytes) - text_tokens(chunk_text or ""))
            stats["tokens_observed_code"] += obs
            stats["savings_hits_measured"] += 1
            _add(stats, repo, user, observed=obs, hits=1)
        for repo, file, meta in candidates:
            k = f"{repo}/{file}"
            if k in counted:
                continue
            nbytes = _int_bytes(meta)
            if nbytes is None:
                continue
            counted.add(k)
            mod = int(MODEL_PCT * file_tokens(nbytes))
            stats["tokens_modeled_code"] += mod
            _add(stats, repo, user, modeled=mod)


def record_notes(stats, store, session_key, hits, bytes_map, user=None, now=None):
    """hits=[(file, chunk_text)]; observed only."""
    with LOCK:
        _prep(stats)
        counted = store.touch(session_key, now)
        for file, chunk_text in hits:
            k = "notes/" + file
            if k in counted:
                continue
            counted.add(k)
            nbytes = _int_bytes({"bytes": (bytes_map or {}).get(file)})
            if nbytes is None:
                stats["savings_hits_unmeasured"] += 1
                _add(stats, "notes", user, hits=1)
                continue
            obs = max(0, file_tokens(nbytes) - text_tokens(chunk_text or ""))
            stats["tokens_observed_notes"] += obs
            stats["savings_hits_measured"] += 1
            _add(stats, "notes", user, observed=obs, hits=1)


_NOTES_CACHE: dict = {}


def notes_bytes_map(graph_path) -> dict:
    """{note id: bytes} from graph_notes.json, cached by mtime. {} on any error."""
    try:
        path = Path(graph_path)
        mtime = path.stat().st_mtime
        cached = _NOTES_CACHE.get(str(path))
        if cached and cached[0] == mtime:
            return cached[1]
        data = json.loads(path.read_text())
        out = {}
        for n in data.get("nodes", []):
            if isinstance(n, dict) and isinstance(n.get("bytes"), int) and "id" in n:
                out[str(n["id"]).replace("\\", "/")] = n["bytes"]
        _NOTES_CACHE[str(path)] = (mtime, out)
        return out
    except Exception:
        return {}


def snapshot(stats: dict) -> dict:
    with LOCK:
        return copy.deepcopy(stats)


def totals(stats: dict) -> tuple:
    def num(k):
        v = stats.get(k, 0)
        return v if isinstance(v, (int, float)) else 0
    obs_code, obs_notes, modeled = num("tokens_observed_code"), num("tokens_observed_notes"), num("tokens_modeled_code")
    return obs_code, obs_notes, modeled, obs_code + obs_notes + modeled


def _vkey(v):
    try:
        return (0, tuple(int(x) for x in str(v).split(".")))
    except ValueError:
        return (1, (), str(v))


def trend(versions: dict) -> list:
    """[(version, total tokens avoided)] sorted numerically by version."""
    out = []
    for v in sorted(versions or {}, key=_vkey):
        s = versions[v]
        out.append((v, totals(s)[3] if isinstance(s, dict) else 0))
    return out


def user_ledger(stats: dict) -> list:
    """[(user, observed+modeled)] sorted descending."""
    by = stats.get("savings_by_user")
    rows = []
    if isinstance(by, dict):
        for u, b in by.items():
            if isinstance(b, dict):
                rows.append((u, (b.get("observed", 0) or 0) + (b.get("modeled", 0) or 0)))
    return sorted(rows, key=lambda r: -r[1])
