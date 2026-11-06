"""Godot support: GDScript semantic chunks, scene/resource/project summaries, graph edges.

Used by chunker.chunk_file (chunks) and code_graph.build_code_graph (edges). Paths handed in
and out are repo-relative POSIX; `res://` paths are resolved against the directory that holds
project.godot (the Godot project root, not necessarily the repo root).
"""

import re
from pathlib import Path

try:
    from tree_sitter import Language, Parser
    import tree_sitter_gdscript as _tsgd
    _GD_LANG = Language(_tsgd.language())
except Exception:  # grammar missing -> chunker falls back to the sliding window
    _GD_LANG = None

GODOT_SUMMARY_EXTS = {".tscn", ".tres", ".godot"}

# ── res:// / uid:// resolution ───────────────────────────────────────────────

_SECTION_RE = re.compile(r'^\[(\w+)([^\]\n]*)\][ \t]*$', re.MULTILINE)  # single line: no cross-line backtracking
MAX_SUMMARY_INPUT = 2_000_000  # chars; larger scenes/resources are truncated before parsing
_ATTR_RE = re.compile(r'(\w+)=("([^"]*)"|[^\s\]]+)')


def _attrs(s: str) -> dict:
    return {m.group(1): (m.group(3) if m.group(3) is not None else m.group(2)) for m in _ATTR_RE.finditer(s)}


class GodotProject:
    """Repo-level Godot context: project roots, autoloads, uid map, class_name map."""

    def __init__(self, repo_path: Path, all_files: set):
        self.roots = sorted({str(Path(f).parent.as_posix()) for f in all_files if Path(f).name == "project.godot"},
                            key=len, reverse=True)
        self.autoloads: dict = {}   # Name -> repo-relative file
        self.uids: dict = {}        # uid://x -> repo-relative file
        self.classes: dict = {}     # class_name -> repo-relative file
        for f in all_files:
            p = repo_path / f
            if Path(f).name == "project.godot":
                for name, target in _parse_autoloads(_read(p)).items():
                    resolved = self.res(target, f)
                    if resolved:
                        self.autoloads[name] = resolved
            elif f.endswith(".gd"):
                m = re.search(r'^class_name\s+(\w+)', _read(p), re.MULTILINE)
                if m:
                    self.classes.setdefault(m.group(1), f)
            if f.endswith((".tscn", ".tres")):
                head = _read(p, 400)
                m = re.search(r'uid="(uid://[^"]+)"', head.split("\n", 1)[0])
                if m:
                    self.uids[m.group(1)] = f
        # `.uid` twin files (Godot 4.4+): script.gd.uid contains the script's uid
        for uidfile in repo_path.rglob("*.uid"):
            try:
                rel = uidfile.relative_to(repo_path).as_posix()[:-4]
                if rel in all_files:
                    self.uids[uidfile.read_text(errors="replace").strip()] = rel
            except Exception:
                continue

    def project_root(self, rel: str) -> str:
        for r in self.roots:
            if r == "." or rel.startswith(r + "/"):
                return r
        return "."

    def res(self, path: str, from_file: str) -> str | None:
        """res://a/b.gd (or uid://...) -> repo-relative path, None if unknown."""
        path = path.strip().lstrip("*")
        if path.startswith("uid://"):
            return self.uids.get(path)
        if not path.startswith("res://"):
            return None
        root = self.project_root(from_file)
        tail = path[len("res://"):]
        return tail if root == "." else f"{root}/{tail}"


def _read(p: Path, limit: int | None = None) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:limit] if limit else text
    except Exception:
        return ""


def _parse_autoloads(text: str) -> dict:
    out, in_section = {}, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_section = s == "[autoload]"
            continue
        if in_section and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


# ── GDScript chunking ────────────────────────────────────────────────────────

_DECL_TYPES = {"signal_statement", "variable_statement", "const_statement", "enum_definition",
               "export_variable_statement", "onready_variable_statement"}


def gd_context(source: str) -> str:
    """'class_name X extends Y' for embedding headers ('' when the file declares neither)."""
    cn = re.search(r'^class_name\s+(\w+)', source, re.MULTILINE)
    ex = re.search(r'^extends\s+(\S+)', source, re.MULTILINE)
    parts = []
    if cn:
        parts.append(f"class_name {cn.group(1)}")
    if ex:
        parts.append(f"extends {ex.group(1)}")
    return " ".join(parts)


def gd_spans(raw: bytes) -> list | None:
    """Top-level semantic spans [(start_line0, end_line_excl, kind)], or None without the grammar.

    Functions and inner classes are their own spans, with preceding annotations (@rpc,
    @warning_ignore ...) attached. Runs of signals/vars/consts/enums form one 'members' span.
    """
    if _GD_LANG is None:
        return None
    try:
        tree = Parser(_GD_LANG).parse(raw)
    except Exception:
        return None
    spans: list = []
    pending_ann = None   # start line of annotations waiting for their declaration
    decl = None          # [start, end] of the current members run
    for node in tree.root_node.children:
        t = node.type
        s, e = node.start_point[0], node.end_point[0] + 1
        if t == "annotation":
            pending_ann = s if pending_ann is None else pending_ann
            continue
        start = pending_ann if pending_ann is not None else s
        pending_ann = None
        if t in ("function_definition", "class_definition", "constructor_definition"):
            if decl:
                spans.append((decl[0], decl[1], "members")); decl = None
            spans.append((start, e, "class" if t == "class_definition" else "function"))
        elif t in _DECL_TYPES:
            decl = [decl[0], e] if decl else [start, e]
        # class_name / extends / comments: covered by the header context
    if decl:
        spans.append((decl[0], decl[1], "members"))
    return spans


# ── Scene / resource / project summaries (indexed instead of raw text) ──────

def _ext_resources(text: str) -> dict:
    out = {}
    for m in _SECTION_RE.finditer(text):
        if m.group(1) == "ext_resource":
            a = _attrs(m.group(2))
            if "id" in a:
                out[a["id"]] = a.get("path") or a.get("uid", "")
    return out


def _sections(text: str):
    """Yield (kind, attrs, body_lines) for each [section] in a .tscn/.tres file."""
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip("\n").splitlines()
        yield m.group(1), _attrs(m.group(2)), body


_EXTRES_REF = re.compile(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)')
_SKIP_VALUE = re.compile(r'^(Packed\w*Array|PoolByteArray|Image)\(')


def summarize_tscn(text: str) -> str:
    ext = _ext_resources(text)
    lines = ["Godot scene", "Nodes:"]
    conns = []
    for kind, a, body in _sections(text):
        if kind == "node":
            name, parent = a.get("name", "?"), a.get("parent")
            path = name if parent is None else (name if parent == "." else f"{parent}/{name}")
            desc = f"  {path}"
            if a.get("type"):
                desc += f" ({a['type']})"
            inst = _EXTRES_REF.search(a.get("instance", ""))
            if inst:
                desc += f" instance={ext.get(inst.group(1), inst.group(1))}"
            for line in body:
                if line.startswith("script ="):
                    ref = _EXTRES_REF.search(line)
                    if ref:
                        desc += f" script={ext.get(ref.group(1), ref.group(1))}"
            lines.append(desc)
        elif kind == "connection":
            conns.append(f"  {a.get('from', '?')}.{a.get('signal', '?')} -> {a.get('method', '?')} (on {a.get('to', '?')})")
    if conns:
        lines.append("Signal connections:")
        lines += conns
    if ext:
        lines.append("Uses: " + ", ".join(sorted(set(v for v in ext.values() if v))))
    return "\n".join(lines)


def summarize_tres(text: str) -> str:
    ext = _ext_resources(text)
    lines = []
    for kind, a, body in _sections(text):
        if kind == "gd_resource":
            head = f"Godot resource type={a.get('type', '?')}"
            if a.get("script_class"):
                head += f" script_class={a['script_class']}"
            lines.append(head)
        elif kind in ("resource", "sub_resource"):
            if kind == "sub_resource":
                lines.append(f"Sub-resource {a.get('type', '')} {a.get('id', '')}".rstrip())
            for line in body:
                if "=" not in line:
                    continue
                k, v = (x.strip() for x in line.split("=", 1))
                if _SKIP_VALUE.match(v):
                    continue
                v = _EXTRES_REF.sub(lambda m: ext.get(m.group(1), m.group(1)), v)
                lines.append(f"  {k} = {v[:200]}")
    if ext:
        lines.append("Uses: " + ", ".join(sorted(set(v for v in ext.values() if v))))
    return "\n".join(lines)


def summarize_project(text: str) -> str:
    lines, section, actions = ["Godot project.godot"], "", []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("["):
            section = s.strip("[]")
            continue
        if "=" not in s or s.startswith(";"):
            continue
        k, v = (x.strip() for x in s.split("=", 1))
        if section == "application" and k in ("config/name", "run/main_scene", "config/features"):
            lines.append(f"{k} = {v}")
        elif section == "autoload":
            lines.append(f"autoload {k} = {v.strip(chr(34)).lstrip('*')}")
        elif section == "input" and not k.startswith(" "):
            actions.append(k)
    if actions:
        lines.append("Input actions: " + ", ".join(actions))
    return "\n".join(lines)


def summarize(path: Path, text: str) -> str:
    text = text[:MAX_SUMMARY_INPUT]
    if path.suffix == ".tscn":
        return summarize_tscn(text)
    if path.suffix == ".tres":
        return summarize_tres(text)
    return summarize_project(text)


# ── Graph edges ──────────────────────────────────────────────────────────────

_RES_STR = re.compile(r'"\*?((?:res|uid)://[^"]+)"')
_LOAD_RE = re.compile(r'\b(?:preload|load|ResourceLoader\.load)\s*\(\s*"((?:res|uid)://[^"]+)"')
_EXTENDS_RE = re.compile(r'^extends\s+("([^"]+)"|(\w+))', re.MULTILINE)
_USE_RE = re.compile(r'\b([A-Z]\w*)\s*(?:\.|\(|$)|(?::|\bas|\bis|->)\s*([A-Z]\w*)', re.MULTILINE)


def gd_edges(rel: str, text: str, proj: GodotProject) -> list:
    """[(target, edge_type)] for a .gd / .tscn / .tres / project.godot file."""
    edges: list = []
    if rel.endswith(".gd"):
        m = _EXTENDS_RE.search(text)
        if m:
            tgt = proj.res(m.group(2), rel) if m.group(2) else proj.classes.get(m.group(3))
            if tgt:
                edges.append((tgt, "inherits"))
        for m in _LOAD_RE.finditer(text):
            tgt = proj.res(m.group(1), rel)
            if tgt:
                edges.append((tgt, "import"))
        used = {a or b for a, b in _USE_RE.findall(text)}
        for name in used:
            tgt = proj.classes.get(name) or proj.autoloads.get(name)
            if tgt:
                edges.append((tgt, "call"))
    else:  # scenes/resources/project: every res:// reference is a dependency
        for m in _RES_STR.finditer(text):
            tgt = proj.res(m.group(1), rel)
            if tgt:
                edges.append((tgt, "import"))
    return [(t, k) for t, k in edges if t != rel]
