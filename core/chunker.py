#!/usr/bin/env python3
"""Source code chunking — tree-sitter semantic parsing with sliding-window fallback."""

from pathlib import Path

CODE_EXTS = {".js", ".ts", ".tsx", ".jsx", ".svelte", ".py", ".java", ".go", ".rs", ".css", ".html", ".kt", ".kts", ".gd", ".yml", ".yaml"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".svelte-kit", "__pycache__", ".gradle", "target"}
LANG_MAP = {
    ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".svelte": "svelte", ".py": "python",
    ".java": "java", ".go": "go", ".rs": "rust", ".css": "css", ".html": "html",
    ".kt": "kotlin", ".kts": "kotlin", ".gd": "gdscript",
    ".yml": "yaml", ".yaml": "yaml",
}

CHUNK_LINES = 30
OVERLAP_LINES = 5
MAX_CHUNK_LINES = 80

try:
    from tree_sitter import Language, Parser as _TSParser
    import tree_sitter_python as _tspy
    import tree_sitter_javascript as _tsjs
    import tree_sitter_typescript as _tsts
    import tree_sitter_kotlin as _tskotlin

    _TS_LANGUAGES: dict = {
        ".py":  Language(_tspy.language()),
        ".js":  Language(_tsjs.language()),
        ".jsx": Language(_tsjs.language()),
        ".ts":  Language(_tsts.language_typescript()),
        ".tsx": Language(_tsts.language_tsx()),
        ".kt":  Language(_tskotlin.language()),
        ".kts": Language(_tskotlin.language()),
    }
    _TS_SEMANTIC: dict = {
        ".py":  {"function_definition", "class_definition"},
        ".js":  {"function_declaration", "class_declaration", "method_definition", "lexical_declaration"},
        ".jsx": {"function_declaration", "class_declaration", "method_definition", "lexical_declaration"},
        ".ts":  {"function_declaration", "class_declaration", "method_definition", "interface_declaration", "lexical_declaration"},
        ".tsx": {"function_declaration", "class_declaration", "method_definition", "interface_declaration", "lexical_declaration"},
        ".kt":  {"function_declaration", "class_declaration", "object_declaration"},
        ".kts": {"function_declaration", "class_declaration", "object_declaration"},
    }
    _TS_AVAILABLE = True
except Exception:
    _TS_AVAILABLE = False
    _TS_LANGUAGES = {}
    _TS_SEMANTIC = {}


def _sliding_window(lines: list, start: int, end: int, repo_name: str, rel: str, language: str, github_url_base: str = "") -> list:
    step = CHUNK_LINES - OVERLAP_LINES
    chunks = []
    i = start
    while i < end:
        j = min(i + CHUNK_LINES, end)
        body = "\n".join(lines[i:j]).strip()
        if body:
            url = f"{github_url_base}/{rel}#L{i+1}-L{j}" if github_url_base else ""
            chunks.append({
                "repo": repo_name, "file": rel, "language": language,
                "start_line": i + 1, "end_line": j,
                "text": f"# {repo_name}/{rel} (lines {i+1}-{j})\n\n{body}",
                "github_url": url,
            })
        if j == end:
            break
        i += step
    return chunks


def _has_function_value(node, depth: int = 0) -> bool:
    if node.type in ("arrow_function", "function_expression"):
        return True
    if depth >= 3:
        return False
    return any(_has_function_value(c, depth + 1) for c in node.children)


def _collect_semantic_nodes(node, target_types: set, depth: int = 0, max_depth: int = 5) -> list:
    if node.type in target_types:
        return [node]
    if depth >= max_depth:
        return []
    result = []
    for child in node.children:
        result.extend(_collect_semantic_nodes(child, target_types, depth + 1, max_depth))
    return result


def chunk_file(path: Path, repo_name: str, base_dir: Path | None = None, github_url_base: str = "") -> list:
    """Chunk a source file into indexable segments.

    base_dir: directory to compute relative paths from (defaults to path.parent).
    github_url_base: e.g. "https://github.com/owner/repo/blob/master"
    """
    try:
        source = path.read_bytes()
        lines = source.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if not lines:
        return []

    ext = path.suffix
    base = base_dir if base_dir else path.parent
    try:
        rel = str(path.relative_to(base))
    except ValueError:
        rel = path.name
    language = LANG_MAP.get(ext, ext.lstrip("."))

    if _TS_AVAILABLE and ext in _TS_LANGUAGES:
        try:
            parser = _TSParser(_TS_LANGUAGES[ext])
            tree = parser.parse(source)
            nodes = _collect_semantic_nodes(tree.root_node, _TS_SEMANTIC[ext])
            nodes = [n for n in nodes if n.type != "lexical_declaration" or _has_function_value(n)]
            if nodes:
                chunks = []
                for node in nodes:
                    s = node.start_point[0]
                    e = node.end_point[0] + 1
                    if e - s > MAX_CHUNK_LINES:
                        chunks.extend(_sliding_window(lines, s, e, repo_name, rel, language, github_url_base))
                    else:
                        body = "\n".join(lines[s:e]).strip()
                        if body:
                            url = f"{github_url_base}/{rel}#L{s+1}-L{e}" if github_url_base else ""
                            chunks.append({
                                "repo": repo_name, "file": rel, "language": language,
                                "start_line": s + 1, "end_line": e,
                                "text": f"# {repo_name}/{rel} (lines {s+1}-{e})\n\n{body}",
                                "github_url": url,
                            })
                return chunks
        except Exception:
            pass

    return _sliding_window(lines, 0, len(lines), repo_name, rel, language, github_url_base)
