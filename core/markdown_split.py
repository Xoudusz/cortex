"""Shared markdown splitter: caps note chunks for embedding (server + local).

No network, no Qdrant."""

import re

MAX_CHUNK_CHARS = 2500  # nomic-embed-text slot is 2048 tokens; dense text runs ~2-3 chars/token
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def _scan_fence(state, text):
    """Fence state after `text`. state = (marker, opening line) or None."""
    for ln in text.split("\n"):
        m = _FENCE.match(ln)
        if not m:
            continue
        mark, info = m.group(1), m.group(2).strip()
        if state is None:
            state = (mark, ln.strip())
        elif mark[0] == state[0][0] and len(mark) >= len(state[0]) and not info:
            state = None
    return state


def _pieces(body: str, room: int) -> list:
    """(text, joiner) pieces of body, each <= room. joiner = separator put before the piece
    when re-assembling: "\\n\\n" at paragraph start, "\\n" at line start, "" inside a hard-split line."""
    out = []
    for pi, para in enumerate(re.split(r"\n\s*\n", body)):
        para_joiner = "\n\n" if pi else ""
        if len(para) <= room:
            out.append((para, para_joiner))
            continue
        buf, buf_joiner = None, None
        for li, ln in enumerate(para.split("\n")):
            line_joiner = (para_joiner if li == 0 else "\n")
            if len(ln) > room:  # overlong line: flush buffer, hard-split the line
                if buf is not None:
                    out.append((buf, buf_joiner))
                    buf = None
                for k in range(0, len(ln), room):
                    out.append((ln[k:k + room], line_joiner if k == 0 else ""))
                continue
            if buf is None:
                buf, buf_joiner = ln, line_joiner
            elif len(buf) + 1 + len(ln) <= room:
                buf += "\n" + ln
            else:
                out.append((buf, buf_joiner))
                buf, buf_joiner = ln, "\n"
        if buf is not None:
            out.append((buf, buf_joiner))
    return out


def split_body(body: str, limit: int = MAX_CHUNK_CHARS) -> list:
    """Split a section body into parts <= limit chars at paragraph / line boundaries.
    A split inside a ``` fence closes it at the part end and reopens it in the next part."""
    if len(body) <= limit:
        return [body]
    room = max(limit - 400, limit // 2)  # reserve for reopened fence line (<=200) + newline + closer
    parts, text, state = [], "", None
    for p, joiner in _pieces(body, room):
        if not text:
            text = p
            state = _scan_fence(state, p)
            continue
        after = _scan_fence(state, p)
        cand = text + joiner + p
        closer = len(after[0]) + 1 if after else 0
        if len(cand) + closer <= limit:
            text, state = cand, after
            continue
        # close the open fence (if any) and start a new part
        parts.append(text + (f"\n{state[0]}" if state else ""))
        reopen = state[1] if state and len(state[1]) <= 200 else ""  # over-long opener: not reopened
        text = (reopen + "\n" + p) if reopen else p
        state = _scan_fence(None, reopen) if reopen else None
        state = _scan_fence(state, p)
    if text:
        parts.append(text)
    return parts


def markdown_chunks(text: str, stem: str, rel: str, tags, modified_at: int) -> list:
    """Shared section → chunk builder for server and local notes indexers.
    One chunk per heading section (split at MAX_CHUNK_CHARS); text prefixed with the heading."""
    chunks = []

    def emit(heading, body):
        budget = max(MAX_CHUNK_CHARS - len(heading) - 22, 500)  # heading prefix + "\n\n" + "(part N)"
        parts = split_body(body, budget)
        for i, part in enumerate(parts, 1):
            h = heading if len(parts) == 1 else f"{heading} (part {i})"
            chunks.append({"heading": h, "text": f"{heading}\n\n{part}",
                           "file": rel, "tags": tags, "modified_at": modified_at})

    current_heading, current_lines = stem, []
    for line in text.splitlines():
        if re.match(r"^#{1,3} ", line):
            body = "\n".join(current_lines).strip()
            if body:
                emit(current_heading, body)
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    body = "\n".join(current_lines).strip()
    if body:
        emit(current_heading, body)
    if not chunks:
        body = text.strip()
        if body:
            chunks.append({"heading": stem, "text": body,
                           "file": rel, "tags": tags, "modified_at": modified_at})
    return chunks
