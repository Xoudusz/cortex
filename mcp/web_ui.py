"""Cortex Web UI — embedded dashboard for search + admin."""

import httpx
from qdrant_client import QdrantClient
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cortex</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --accent-hover: #79b8ff;
            --success: #3fb950;
            --error: #f85149;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 1rem;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { font-size: 1.5rem; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
        h1 span { color: var(--text-muted); font-weight: normal; font-size: 0.875rem; }

        .tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.5rem;
        }
        .tab {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            cursor: pointer;
            border-radius: 6px;
            font-size: 0.875rem;
        }
        .tab:hover { background: var(--surface); color: var(--text); }
        .tab.active { background: var(--surface); color: var(--accent); }

        .panel { display: none; }
        .panel.active { display: block; }

        .search-form {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        input[type="text"] {
            flex: 1;
            padding: 0.75rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text);
            font-size: 0.875rem;
        }
        input[type="text"]:focus { outline: none; border-color: var(--accent); }
        input[type="text"]::placeholder { color: var(--text-muted); }

        button {
            padding: 0.75rem 1.25rem;
            background: var(--accent);
            border: none;
            border-radius: 6px;
            color: #fff;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 500;
        }
        button:hover { background: var(--accent-hover); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        button.secondary {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
        }
        button.secondary:hover { border-color: var(--accent); }

        .toggles {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .toggle {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            color: var(--text-muted);
        }
        .toggle input { accent-color: var(--accent); }

        .results { display: flex; flex-direction: column; gap: 0.75rem; }
        .result-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
        }
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.5rem;
        }
        .result-title {
            font-weight: 600;
            font-size: 0.875rem;
            color: var(--accent);
            word-break: break-all;
        }
        .result-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-align: right;
        }
        .result-content {
            font-size: 0.8125rem;
            color: var(--text-muted);
            white-space: pre-wrap;
            max-height: 200px;
            overflow-y: auto;
            background: var(--bg);
            padding: 0.75rem;
            border-radius: 4px;
            font-family: 'SF Mono', Consolas, monospace;
        }
        .result-tags {
            margin-top: 0.5rem;
            display: flex;
            gap: 0.25rem;
            flex-wrap: wrap;
        }
        .tag {
            background: var(--bg);
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
        }
        .stat-label { font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem; }
        .stat-value { font-size: 1.5rem; font-weight: 600; }
        .stat-value.ok { color: var(--success); }
        .stat-value.error { color: var(--error); }

        .reindex-section { margin-top: 1.5rem; }
        .reindex-buttons { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
        .status-log {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            font-family: 'SF Mono', Consolas, monospace;
            font-size: 0.75rem;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            color: var(--text-muted);
        }
        .status-running { border-color: var(--accent); }

        .message {
            padding: 0.75rem 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
            font-size: 0.875rem;
        }
        .message.error { background: rgba(248, 81, 73, 0.1); color: var(--error); }
        .message.info { background: rgba(88, 166, 255, 0.1); color: var(--accent); }

        .empty { color: var(--text-muted); font-style: italic; }
        .loading { opacity: 0.6; }

        a { color: var(--accent); text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Cortex <span>RAG Dashboard</span></h1>

        <div class="tabs">
            <button class="tab active" data-tab="search">Search</button>
            <button class="tab" data-tab="admin">Admin</button>
        </div>

        <div id="search-panel" class="panel active">
            <form class="search-form" id="search-form">
                <input type="text" id="query" placeholder="Search notes and code..." autofocus>
                <button type="submit">Search</button>
            </form>
            <div class="toggles">
                <label class="toggle">
                    <input type="checkbox" id="search-notes" checked>
                    <span>Notes</span>
                </label>
                <label class="toggle">
                    <input type="checkbox" id="search-code" checked>
                    <span>Code</span>
                </label>
            </div>
            <div id="search-results" class="results"></div>
        </div>

        <div id="admin-panel" class="panel">
            <div class="stats-grid" id="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Notes indexed</div>
                    <div class="stat-value" id="stat-notes">—</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Code chunks indexed</div>
                    <div class="stat-value" id="stat-code">—</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Ollama status</div>
                    <div class="stat-value" id="stat-ollama">—</div>
                </div>
            </div>

            <div class="reindex-section">
                <h3 style="margin-bottom: 0.75rem; font-size: 1rem;">Reindex</h3>
                <div class="reindex-buttons">
                    <button id="reindex-all">Reindex All</button>
                    <button id="reindex-notes" class="secondary">Notes Only</button>
                    <button id="reindex-code" class="secondary">Code Only</button>
                </div>
                <div id="reindex-status" class="status-log">No reindex running.</div>
            </div>
        </div>
    </div>

    <script>
        const API_KEY = localStorage.getItem('cortex_api_key') || new URLSearchParams(location.search).get('key');
        if (API_KEY) {
            localStorage.setItem('cortex_api_key', API_KEY);
            if (location.search.includes('key=')) {
                history.replaceState(null, '', location.pathname);
            }
        }

        async function api(path, options = {}) {
            const res = await fetch(path, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': API_KEY || '',
                    ...options.headers
                }
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        }

        // Tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab + '-panel').classList.add('active');
                if (tab.dataset.tab === 'admin') loadStats();
            });
        });

        // Search
        const searchForm = document.getElementById('search-form');
        const queryInput = document.getElementById('query');
        const resultsDiv = document.getElementById('search-results');

        searchForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const query = queryInput.value.trim();
            if (!query) return;

            const collections = [];
            if (document.getElementById('search-notes').checked) collections.push('notes');
            if (document.getElementById('search-code').checked) collections.push('code');
            if (!collections.length) {
                resultsDiv.innerHTML = '<div class="message error">Select at least one collection</div>';
                return;
            }

            resultsDiv.innerHTML = '<div class="empty loading">Searching...</div>';
            try {
                const data = await api('/api/search', {
                    method: 'POST',
                    body: JSON.stringify({ query, collections, limit: 10 })
                });
                renderResults(data);
            } catch (err) {
                resultsDiv.innerHTML = '<div class="message error">' + err.message + '</div>';
            }
        });

        function renderResults(data) {
            const all = [
                ...(data.notes || []).map(r => ({ ...r, type: 'note' })),
                ...(data.code || []).map(r => ({ ...r, type: 'code' }))
            ].sort((a, b) => b.score - a.score);

            if (!all.length) {
                resultsDiv.innerHTML = '<div class="empty">No results found.</div>';
                return;
            }

            resultsDiv.innerHTML = all.map(r => {
                if (r.type === 'note') {
                    const tags = (r.tags || []).map(t => '<span class="tag">' + t + '</span>').join('');
                    return '<div class="result-card">' +
                        '<div class="result-header">' +
                        '<div class="result-title">' + r.file + ' › ' + r.heading + '</div>' +
                        '<div class="result-meta">score: ' + r.score.toFixed(3) + '</div>' +
                        '</div>' +
                        '<div class="result-content">' + escapeHtml(r.text) + '</div>' +
                        (tags ? '<div class="result-tags">' + tags + '</div>' : '') +
                        '</div>';
                } else {
                    const link = r.github_url ? '<a href="' + r.github_url + '" target="_blank">GitHub</a>' : '';
                    return '<div class="result-card">' +
                        '<div class="result-header">' +
                        '<div class="result-title">' + r.repo + '/' + r.file + ':' + r.start_line + '-' + r.end_line + '</div>' +
                        '<div class="result-meta">' + (r.language || '') + ' • score: ' + r.score.toFixed(3) + (link ? ' • ' + link : '') + '</div>' +
                        '</div>' +
                        '<div class="result-content">' + escapeHtml(r.text) + '</div>' +
                        '</div>';
                }
            }).join('');
        }

        function escapeHtml(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // Stats
        async function loadStats() {
            try {
                const data = await api('/api/stats');
                document.getElementById('stat-notes').textContent = data.notes?.points_count?.toLocaleString() ?? '—';
                document.getElementById('stat-code').textContent = data.code?.points_count?.toLocaleString() ?? '—';
                const ollama = document.getElementById('stat-ollama');
                ollama.textContent = data.ollama?.status || 'error';
                ollama.className = 'stat-value ' + (data.ollama?.status === 'ok' ? 'ok' : 'error');
            } catch (err) {
                console.error('Failed to load stats:', err);
            }
        }

        // Reindex
        let statusPoll = null;

        document.getElementById('reindex-all').addEventListener('click', () => triggerReindex(true, true));
        document.getElementById('reindex-notes').addEventListener('click', () => triggerReindex(true, false));
        document.getElementById('reindex-code').addEventListener('click', () => triggerReindex(false, true));

        async function triggerReindex(notes, code) {
            try {
                const data = await api('/api/reindex', {
                    method: 'POST',
                    body: JSON.stringify({ notes, code, repo: '' })
                });
                if (data.status === 'started' || data.status === 'already_running') {
                    pollStatus();
                }
            } catch (err) {
                document.getElementById('reindex-status').textContent = 'Error: ' + err.message;
            }
        }

        async function pollStatus() {
            if (statusPoll) clearInterval(statusPoll);
            const statusDiv = document.getElementById('reindex-status');
            statusDiv.classList.add('status-running');

            const update = async () => {
                try {
                    const data = await api('/api/status');
                    let text = 'Status: ' + (data.running ? 'running' : 'done') + ' (' + Math.round(data.elapsed_seconds) + 's)\\n\\n';
                    text += (data.output || []).join('\\n');
                    if (data.error) text += '\\n\\nError: ' + data.error;
                    statusDiv.textContent = text;
                    statusDiv.scrollTop = statusDiv.scrollHeight;

                    if (data.done && !data.running) {
                        clearInterval(statusPoll);
                        statusPoll = null;
                        statusDiv.classList.remove('status-running');
                        loadStats();
                    }
                } catch (err) {
                    statusDiv.textContent = 'Error polling status: ' + err.message;
                }
            };

            await update();
            statusPoll = setInterval(update, 2000);
        }

        // Initial status check
        api('/api/status').then(data => {
            if (data.running) pollStatus();
            else if (data.done) {
                let text = 'Last run: ' + (data.running ? 'running' : 'done') + ' (' + Math.round(data.elapsed_seconds) + 's)\\n\\n';
                text += (data.output || []).join('\\n');
                document.getElementById('reindex-status').textContent = text;
            }
        }).catch(() => {});
    </script>
</body>
</html>"""


async def ui(request: Request) -> HTMLResponse:
    """Serve the web UI."""
    return HTMLResponse(UI_HTML)


async def api_search(request: Request, qdrant_url: str, embed_fn) -> JSONResponse:
    """Search notes and/or code collections."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    query = body.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "Query required"}, status_code=400)

    collections = body.get("collections", ["notes", "code"])
    limit = min(body.get("limit", 10), 50)

    client = QdrantClient(url=qdrant_url)
    vector = embed_fn(query)
    result = {}

    if "notes" in collections:
        try:
            points = client.query_points("notes", query=vector, limit=limit, with_payload=True).points
            result["notes"] = [
                {
                    "file": p.payload.get("file", ""),
                    "heading": p.payload.get("heading", ""),
                    "text": p.payload.get("text", ""),
                    "tags": p.payload.get("tags", []),
                    "score": round(p.score, 4)
                }
                for p in points
            ]
        except Exception as e:
            result["notes"] = []
            result["notes_error"] = str(e)

    if "code" in collections:
        try:
            points = client.query_points("code", query=vector, limit=limit, with_payload=True).points
            result["code"] = [
                {
                    "repo": p.payload.get("repo", ""),
                    "file": p.payload.get("file", ""),
                    "start_line": p.payload.get("start_line", 0),
                    "end_line": p.payload.get("end_line", 0),
                    "language": p.payload.get("language", ""),
                    "text": p.payload.get("text", ""),
                    "github_url": p.payload.get("github_url", ""),
                    "score": round(p.score, 4)
                }
                for p in points
            ]
        except Exception as e:
            result["code"] = []
            result["code_error"] = str(e)

    return JSONResponse(result)


async def api_status(request: Request, reindex_state: dict) -> JSONResponse:
    """Get reindex status."""
    import time
    s = reindex_state
    if s["started_at"] is None:
        return JSONResponse({
            "running": False,
            "elapsed_seconds": 0,
            "output": [],
            "error": None,
            "done": False
        })

    elapsed = time.time() - s["started_at"]
    return JSONResponse({
        "running": s["running"],
        "elapsed_seconds": round(elapsed, 1),
        "output": s["output"][-100:],  # Last 100 lines
        "error": s["error"],
        "done": s["done"]
    })


async def api_reindex(request: Request, reindex_lock, reindex_state: dict, run_reindex_fn) -> JSONResponse:
    """Trigger reindex."""
    import threading

    try:
        body = await request.json()
    except Exception:
        body = {}

    notes = body.get("notes", True)
    code = body.get("code", True)
    repo = body.get("repo", "")

    with reindex_lock:
        if reindex_state["running"]:
            return JSONResponse({"status": "already_running"})
        threading.Thread(target=run_reindex_fn, args=(notes, code, repo), daemon=True).start()

    return JSONResponse({"status": "started"})


async def api_stats(request: Request, qdrant_url: str, ollama_url: str) -> JSONResponse:
    """Get collection stats and service status."""
    client = QdrantClient(url=qdrant_url)
    result = {}

    # Notes collection
    try:
        info = client.get_collection("notes")
        result["notes"] = {"points_count": info.points_count}
    except Exception as e:
        result["notes"] = {"error": str(e)}

    # Code collection
    try:
        info = client.get_collection("code")
        result["code"] = {"points_count": info.points_count}
    except Exception as e:
        result["code"] = {"error": str(e)}

    # Ollama status
    try:
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=5)
        result["ollama"] = {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception:
        result["ollama"] = {"status": "error"}

    return JSONResponse(result)
