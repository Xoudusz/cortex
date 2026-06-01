"""Cortex Web UI — API handlers for search, status, stats, and reindex."""

import time

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from template import LOGO_SVG, UI_HTML  # noqa: F401 (LOGO_SVG re-exported for favicon route)


async def ui(request: Request) -> HTMLResponse:
    """Serve the web dashboard HTML."""
    return HTMLResponse(UI_HTML)


async def api_search(request: Request, qdrant_url: str, embed_fn) -> JSONResponse:
    """Semantic search over notes and/or code collections; returns scored results."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    query = body.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "Query required"}, status_code=400)
    collections = body.get("collections", ["notes", "code"])
    limit = min(body.get("limit", 10), 50)
    repo_filter = body.get("repo", "").strip()
    client = QdrantClient(url=qdrant_url)
    vector = embed_fn(query)
    result = {}
    if "notes" in collections:
        try:
            points = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
            result["notes"] = [{"file": p.payload.get("file", ""), "heading": p.payload.get("heading", ""), "text": p.payload.get("text", ""), "tags": p.payload.get("tags", []), "score": round(p.score, 4)} for p in points]
        except Exception as e:
            result["notes"] = []; result["notes_error"] = str(e)
    if "code" in collections:
        try:
            q_filter = Filter(must=[FieldCondition(key="repo", match=MatchValue(value=repo_filter))]) if repo_filter else None
            points = client.query_points("code", query=vector, limit=limit, with_payload=True, query_filter=q_filter).points
            result["code"] = [{"repo": p.payload.get("repo", ""), "file": p.payload.get("file", ""), "start_line": p.payload.get("start_line", 0), "end_line": p.payload.get("end_line", 0), "language": p.payload.get("language", ""), "text": p.payload.get("text", ""), "github_url": p.payload.get("github_url", ""), "score": round(p.score, 4)} for p in points]
        except Exception as e:
            result["code"] = []; result["code_error"] = str(e)
    return JSONResponse(result)


async def api_status(request: Request, reindex_state: dict, job_queue: list = None) -> JSONResponse:
    """Return current reindex job state, elapsed time, output tail, and queue snapshot."""
    s = reindex_state
    base = {"running": False, "elapsed_seconds": 0, "output": [], "error": None, "done": False, "queue": job_queue or [], "current_job": None}
    if s["started_at"] is None:
        return JSONResponse(base)
    if s["running"]:
        elapsed = time.time() - s["started_at"]
    elif s["finished_at"]:
        elapsed = s["finished_at"] - s["started_at"]
    else:
        elapsed = 0
    return JSONResponse({**base, "running": s["running"], "elapsed_seconds": round(elapsed, 1), "output": s["output"][-100:], "error": s["error"], "done": s["done"], "current_job": s.get("current_job")})


async def api_stats(request: Request, qdrant_url: str, ollama_url: str, graph_stats: dict = None) -> JSONResponse:
    """Return Qdrant collection point counts, Ollama status, and optional graph stats payload."""
    client = QdrantClient(url=qdrant_url)
    result = {}
    try:
        info = client.get_collection("notes"); result["notes"] = {"points_count": info.points_count}
    except Exception as e:
        result["notes"] = {"error": str(e)}
    try:
        info = client.get_collection("code"); result["code"] = {"points_count": info.points_count}
    except Exception as e:
        result["code"] = {"error": str(e)}
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5)
        result["ollama"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception:
        result["ollama"] = {"status": "error"}
    if graph_stats is not None:
        result["graph"] = dict(graph_stats)
    return JSONResponse(result)
