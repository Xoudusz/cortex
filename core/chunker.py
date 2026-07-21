#!/usr/bin/env python3
"""Source code chunking — tree-sitter semantic parsing with sliding-window fallback."""

import fnmatch
import os
import re as _re
from pathlib import Path

_RAZOR_BLOCK_RE = _re.compile(r'@(?:code|functions)\s*\{', _re.IGNORECASE)


def _extract_razor_cs_blocks(source: str) -> list:
    """Extract @code{} and @functions{} C# blocks from Razor markup using brace counting."""
    blocks = []
    for match in _RAZOR_BLOCK_RE.finditer(source):
        open_pos = source.index('{', match.start())
        depth = 0
        j = open_pos
        while j < len(source):
            if source[j] == '{':
                depth += 1
            elif source[j] == '}':
                depth -= 1
                if depth == 0:
                    start_line = source[:open_pos].count('\n') + 2  # line after opening {
                    end_line = source[:j].count('\n') + 1           # line of closing }
                    if end_line > start_line:
                        blocks.append({"start_line": start_line, "end_line": end_line})
                    break
            j += 1
    return blocks

REPOS_DIR = Path(os.environ.get("REPOS_DIR", "/tmp/repos"))

CODE_EXTS = {".js", ".ts", ".tsx", ".jsx", ".svelte", ".py", ".java", ".go", ".rs", ".css", ".html", ".kt", ".kts", ".gd", ".yml", ".yaml", ".cs", ".razor", ".cshtml"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".svelte-kit", "__pycache__", ".gradle", "target", "bin", "obj"}
LANG_MAP = {
    ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript", ".svelte": "svelte", ".py": "python",
    ".java": "java", ".go": "go", ".rs": "rust", ".css": "css", ".html": "html",
    ".kt": "kotlin", ".kts": "kotlin", ".gd": "gdscript",
    ".yml": "yaml", ".yaml": "yaml", ".cs": "csharp",
    ".razor": "razor", ".cshtml": "cshtml",
}

def _is_excluded(rel: str, patterns: list) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in patterns)


CHUNK_LINES = 30
OVERLAP_LINES = 5
MAX_CHUNK_LINES = 80

_FRAMEWORK_FILENAMES = {
    # SvelteKit route/hook conventions
    "hooks.server":    "sveltekit server hooks handle",
    "hooks.client":    "sveltekit client hooks",
    "+page":           "sveltekit page component",
    "+layout":         "sveltekit layout component",
    "+server":         "sveltekit api route endpoint",
    "+page.server":    "sveltekit page server load action",
    "+layout.server":  "sveltekit layout server load",
    "+error":          "sveltekit error page",
    # Framework config files (unambiguous)
    "svelte.config":   "sveltekit",
    "next.config":     "nextjs",
    "nuxt.config":     "nuxt",
    "astro.config":    "astro",
    "remix.config":    "remix",
    # Next.js pages router conventions
    "_app":            "nextjs",
    "_document":       "nextjs",
}

_FRAMEWORK_IMPORTS = [
    # JS/TS frameworks
    ("@sveltejs/kit",          "sveltekit"),
    ("from 'react'",           "react"),
    ('from "react"',           "react"),
    ("from 'next/",            "nextjs"),
    ('from "next/',            "nextjs"),
    ("from 'vue'",             "vue"),
    ('from "vue"',             "vue"),
    ("@angular/core",          "angular"),
    ("from 'express'",         "express"),
    ('from "express"',         "express"),
    ("from 'fastify'",         "fastify"),
    ('from "fastify"',         "fastify"),
    ("from 'solid-js'",        "solidjs"),
    ('from "solid-js"',        "solidjs"),
    ("@remix-run/",            "remix"),
    ("from 'astro'",           "astro"),
    ('from "astro"',           "astro"),
    # Python frameworks
    ("from fastapi",           "fastapi"),
    ("import fastapi",         "fastapi"),
    ("from django",            "django"),
    ("import django",          "django"),
    ("from flask",             "flask"),
    ("import flask",           "flask"),
    ("from starlette",         "starlette"),
    ("from pydantic",          "pydantic"),
    ("from sqlalchemy",        "sqlalchemy"),
    # Python ML/data
    ("import torch",           "pytorch"),
    ("from torch",             "pytorch"),
    ("import tensorflow",      "tensorflow"),
    ("from tensorflow",        "tensorflow"),
    ("import numpy",           "numpy"),
    ("import pandas",          "pandas"),
    ("from sklearn",           "scikit-learn"),
    ("from transformers",      "huggingface"),
    ("from qdrant_client",     "qdrant"),
    ("from fastembed",         "fastembed"),
    # Kotlin/Java
    ("import io.ktor",         "ktor"),
    ("import org.springframework", "spring"),
    ("import androidx",        "android"),
    # Go
    ("gin-gonic/gin",          "gin"),
    ("gofiber/fiber",          "fiber"),
    # Rust
    ("use actix",              "actix"),
    ("use axum",               "axum"),
    ("use tokio",              "tokio"),
    # C#
    ("using Microsoft.AspNetCore",       "aspnetcore"),
    ("using Microsoft.Extensions",       "aspnetcore"),
    ("using Microsoft.EntityFrameworkCore", "entityframework"),
    ("using Newtonsoft.Json",            "newtonsoft"),
    ("using System.Text.Json",           "system-text-json"),
    ("using Xunit",                      "xunit"),
    ("using NUnit.Framework",            "nunit"),
    ("using Microsoft.Azure",            "azure-sdk"),
]

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
    try:
        import tree_sitter_c_sharp as _tscs
        _TS_LANGUAGES[".cs"] = Language(_tscs.language())
        _TS_SEMANTIC[".cs"] = {
            "method_declaration", "class_declaration", "interface_declaration",
            "constructor_declaration", "struct_declaration", "enum_declaration",
        }
    except Exception:
        pass
    _TS_AVAILABLE = True
except Exception:
    _TS_AVAILABLE = False
    _TS_LANGUAGES = {}
    _TS_SEMANTIC = {}


def _path_tokens(repo_name: str, rel: str) -> str:
    parts = [repo_name.replace("-", " ").replace("_", " ")]
    for p in Path(rel).parts[:-1]:
        parts.append(p.replace("-", " ").replace("_", " "))
    stem = Path(rel).stem.replace("-", " ").replace("_", " ").replace(".", " ")
    parts.append(stem)
    return " ".join(parts)


def _extra_tokens(rel: str, lines: list) -> str:
    stem = Path(rel).stem
    parts = []
    if stem in _FRAMEWORK_FILENAMES:
        parts.append(_FRAMEWORK_FILENAMES[stem])
    header = "\n".join(lines[:50])
    seen = set(parts)
    for pattern, framework in _FRAMEWORK_IMPORTS:
        if pattern in header and framework not in seen:
            parts.append(framework)
            seen.add(framework)
    return " ".join(parts)


def _sliding_window(lines: list, start: int, end: int, repo_name: str, rel: str, language: str, github_url_base: str = "", extra_tokens: str = "") -> list:
    step = CHUNK_LINES - OVERLAP_LINES
    chunks = []
    i = start
    while i < end:
        j = min(i + CHUNK_LINES, end)
        body = "\n".join(lines[i:j]).strip()
        if body:
            url = f"{github_url_base}/{rel}#L{i+1}-L{j}" if github_url_base else ""
            tokens = _path_tokens(repo_name, rel)
            header = f"# {repo_name}/{rel} (lines {i+1}-{j})\n# {tokens}"
            if extra_tokens:
                header += f"\n# {extra_tokens}"
            chunks.append({
                "repo": repo_name, "file": rel, "language": language,
                "start_line": i + 1, "end_line": j,
                "text": f"{header}\n\n{body}",
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


def chunk_file(path: Path, repo_name: str, base_dir: Path | None = None, github_url_base: str = "", roslyn_data: dict | None = None) -> list:
    """Chunk a source file into indexable segments.

    base_dir: directory to compute relative paths from (defaults to path.parent).
    github_url_base: e.g. "https://github.com/owner/repo/blob/master"
    roslyn_data: per-file Roslyn analysis dict with "symbols" and "typeRefs" keys.
    """
    try:
        raw = path.read_bytes()
        source_text = raw.decode("utf-8", errors="replace")
        lines = source_text.splitlines()
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
    extra = _extra_tokens(rel, lines)

    def _header(rel: str, s: int, e: int, tokens: str) -> str:
        h = f"# {repo_name}/{rel} (lines {s}-{e})\n# {tokens}"
        return h + f"\n# {extra}" if extra else h

    # Razor/Blazor: extract @code blocks as csharp + whole file as razor context
    if ext in (".razor", ".cshtml"):
        chunks = []
        blocks = _extract_razor_cs_blocks(source_text)
        for block in blocks:
            s, e = block["start_line"], block["end_line"]
            body = "\n".join(lines[s - 1:e]).strip()
            if body:
                url = f"{github_url_base}/{rel}#L{s}-L{e}" if github_url_base else ""
                tokens = _path_tokens(repo_name, rel)
                chunks.append({
                    "repo": repo_name, "file": rel, "language": "csharp",
                    "start_line": s, "end_line": e,
                    "text": f"{_header(rel, s, e, tokens)}\n\n{body}",
                    "github_url": url,
                })
        # Always include a full-file razor chunk for markup context
        body = "\n".join(lines).strip()
        if body:
            url = f"{github_url_base}/{rel}#L1-L{len(lines)}" if github_url_base else ""
            tokens = _path_tokens(repo_name, rel)
            chunks.append({
                "repo": repo_name, "file": rel, "language": language,
                "start_line": 1, "end_line": len(lines),
                "text": f"{_header(rel, 1, len(lines), tokens)}\n\n{body}",
                "github_url": url,
            })
        return chunks

    # Small files: keep as single chunk to avoid diluting path/filename signal
    if len(lines) <= MAX_CHUNK_LINES:
        body = "\n".join(lines).strip()
        if body:
            url = f"{github_url_base}/{rel}#L1-L{len(lines)}" if github_url_base else ""
            tokens = _path_tokens(repo_name, rel)
            return [{
                "repo": repo_name, "file": rel, "language": language,
                "start_line": 1, "end_line": len(lines),
                "text": f"{_header(rel, 1, len(lines), tokens)}\n\n{body}",
                "github_url": url,
            }]
        return []

    # Roslyn semantic chunking for .cs (preferred over tree-sitter when available)
    if roslyn_data and ext == ".cs":
        top_level_kinds = {"class", "interface", "struct", "enum", "record"}
        all_syms = roslyn_data.get("symbols", [])
        syms = [s for s in all_syms if s.get("kind") in top_level_kinds] or all_syms
        if syms:
            chunks = []
            for sym in syms:
                s = sym["startLine"] - 1  # 0-indexed
                e = sym["endLine"]
                if e - s > MAX_CHUNK_LINES:
                    chunks.extend(_sliding_window(lines, s, e, repo_name, rel, language, github_url_base, extra))
                else:
                    body = "\n".join(lines[s:e]).strip()
                    if body:
                        url = f"{github_url_base}/{rel}#L{s+1}-L{e}" if github_url_base else ""
                        tokens = _path_tokens(repo_name, rel)
                        chunks.append({
                            "repo": repo_name, "file": rel, "language": language,
                            "start_line": s + 1, "end_line": e,
                            "text": f"{_header(rel, s+1, e, tokens)}\n\n{body}",
                            "github_url": url,
                        })
            if chunks:
                return chunks

    if _TS_AVAILABLE and ext in _TS_LANGUAGES:
        try:
            parser = _TSParser(_TS_LANGUAGES[ext])
            tree = parser.parse(raw)
            nodes = _collect_semantic_nodes(tree.root_node, _TS_SEMANTIC[ext])
            nodes = [n for n in nodes if n.type != "lexical_declaration" or _has_function_value(n)]
            if nodes:
                chunks = []
                for node in nodes:
                    s = node.start_point[0]
                    e = node.end_point[0] + 1
                    if e - s > MAX_CHUNK_LINES:
                        chunks.extend(_sliding_window(lines, s, e, repo_name, rel, language, github_url_base, extra))
                    else:
                        body = "\n".join(lines[s:e]).strip()
                        if body:
                            url = f"{github_url_base}/{rel}#L{s+1}-L{e}" if github_url_base else ""
                            tokens = _path_tokens(repo_name, rel)
                            chunks.append({
                                "repo": repo_name, "file": rel, "language": language,
                                "start_line": s + 1, "end_line": e,
                                "text": f"{_header(rel, s+1, e, tokens)}\n\n{body}",
                                "github_url": url,
                            })
                return chunks
        except Exception:
            pass

    return _sliding_window(lines, 0, len(lines), repo_name, rel, language, github_url_base, extra)
