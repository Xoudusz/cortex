"""Cortex Web UI — embedded dashboard for search + admin."""

import httpx
from qdrant_client import QdrantClient
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

FAVICON = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><line x1='12' y1='3' x2='4' y2='9' stroke='%238b5cf6' stroke-width='1.2' stroke-linecap='round'/><line x1='12' y1='3' x2='20' y2='9' stroke='%238b5cf6' stroke-width='1.2' stroke-linecap='round'/><line x1='4' y1='9' x2='4' y2='15' stroke='%238b5cf6' stroke-width='1.2' stroke-linecap='round'/><line x1='20' y1='9' x2='20' y2='15' stroke='%238b5cf6' stroke-width='1.2' stroke-linecap='round'/><line x1='4' y1='15' x2='12' y2='21' stroke='%238b5cf6' stroke-width='1.2' stroke-linecap='round'/><line x1='20' y1='15' x2='12' y2='21' stroke='%238b5cf6' stroke-width='1.2' stroke-linecap='round'/><line x1='4' y1='9' x2='12' y2='12' stroke='%237c3aed' stroke-width='1' stroke-linecap='round'/><line x1='20' y1='9' x2='12' y2='12' stroke='%237c3aed' stroke-width='1' stroke-linecap='round'/><line x1='4' y1='15' x2='12' y2='12' stroke='%237c3aed' stroke-width='1' stroke-linecap='round'/><line x1='20' y1='15' x2='12' y2='12' stroke='%237c3aed' stroke-width='1' stroke-linecap='round'/><circle cx='12' cy='3' r='2.5' fill='%23a78bfa'/><circle cx='4' cy='9' r='2' fill='%238b5cf6'/><circle cx='20' cy='9' r='2' fill='%238b5cf6'/><circle cx='12' cy='12' r='2.5' fill='%23a78bfa'/><circle cx='4' cy='15' r='2' fill='%238b5cf6'/><circle cx='20' cy='15' r='2' fill='%238b5cf6'/><circle cx='12' cy='21' r='2.5' fill='%23a78bfa'/></svg>"

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" class="logo-svg">
  <defs>
    <linearGradient id="cg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#c084fc"/>
      <stop offset="100%" stop-color="#7c3aed"/>
    </linearGradient>
  </defs>
  <line x1="12" y1="3" x2="4" y2="9" stroke="#8b5cf6" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="12" y1="3" x2="20" y2="9" stroke="#8b5cf6" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="4" y1="9" x2="4" y2="15" stroke="#8b5cf6" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="20" y1="9" x2="20" y2="15" stroke="#8b5cf6" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="4" y1="15" x2="12" y2="21" stroke="#8b5cf6" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="20" y1="15" x2="12" y2="21" stroke="#8b5cf6" stroke-width="1.2" stroke-linecap="round"/>
  <line x1="4" y1="9" x2="12" y2="12" stroke="#7c3aed" stroke-width="1" stroke-linecap="round"/>
  <line x1="20" y1="9" x2="12" y2="12" stroke="#7c3aed" stroke-width="1" stroke-linecap="round"/>
  <line x1="4" y1="15" x2="12" y2="12" stroke="#7c3aed" stroke-width="1" stroke-linecap="round"/>
  <line x1="20" y1="15" x2="12" y2="12" stroke="#7c3aed" stroke-width="1" stroke-linecap="round"/>
  <circle cx="12" cy="3" r="2.5" fill="url(#cg)"/>
  <circle cx="4" cy="9" r="2" fill="#8b5cf6"/>
  <circle cx="20" cy="9" r="2" fill="#8b5cf6"/>
  <circle cx="12" cy="12" r="2.5" fill="url(#cg)"/>
  <circle cx="4" cy="15" r="2" fill="#8b5cf6"/>
  <circle cx="20" cy="15" r="2" fill="#8b5cf6"/>
  <circle cx="12" cy="21" r="2.5" fill="url(#cg)"/>
</svg>"""

_UI_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cortex</title>
    <link rel="icon" type="image/svg+xml" href="__FAVICON__">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg: #0d0f14;
            --surface: #13161e;
            --border: #252a38;
            --text: #e2e8f0;
            --text-muted: #7c8698;
            --accent: #a78bfa;
            --accent-hover: #c084fc;
            --accent-dim: rgba(167, 139, 250, 0.12);
            --accent-glow: rgba(167, 139, 250, 0.2);
            --success: #34d399;
            --error: #f87171;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 1.5rem 1rem;
        }
        .container { max-width: 900px; margin: 0 auto; }

        .header {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1.25rem;
            border-bottom: 1px solid var(--border);
        }
        .logo-svg { width: 28px; height: 28px; flex-shrink: 0; }
        .header-text h1 {
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.01em;
            background: linear-gradient(135deg, #c084fc, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header-text span { font-size: 0.75rem; color: var(--text-muted); }

        .tabs {
            display: flex;
            gap: 0.25rem;
            margin-bottom: 1.5rem;
            background: var(--surface);
            padding: 0.25rem;
            border-radius: 8px;
            width: fit-content;
        }
        .tab {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 0.4rem 1rem;
            cursor: pointer;
            border-radius: 6px;
            font-size: 0.8125rem;
            font-weight: 500;
            transition: all 0.15s;
        }
        .tab:hover { color: var(--text); }
        .tab.active {
            background: var(--accent-dim);
            color: var(--accent);
            box-shadow: inset 0 0 0 1px rgba(167,139,250,0.25);
        }

        .panel { display: none; }
        .panel.active { display: block; }

        .search-form { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
        input[type="text"] {
            flex: 1;
            padding: 0.625rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 0.875rem;
            transition: border-color 0.15s;
        }
        input[type="text"]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        input[type="text"]::placeholder { color: var(--text-muted); }

        select {
            width: 100%;
            padding: 0.625rem 1rem;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 0.875rem;
            margin-bottom: 0.5rem;
            cursor: pointer;
        }
        select:focus { outline: none; border-color: var(--accent); }

        button {
            padding: 0.625rem 1.25rem;
            background: var(--accent);
            border: none;
            border-radius: 8px;
            color: #fff;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.15s;
        }
        button:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 4px 12px var(--accent-glow); }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }
        button.secondary {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-muted);
        }
        button.secondary:hover { border-color: var(--accent); color: var(--accent); box-shadow: none; }
        button.small { padding: 0.3rem 0.7rem; font-size: 0.75rem; }
        button.danger {
            background: rgba(248, 113, 113, 0.1);
            border: 1px solid rgba(248, 113, 113, 0.3);
            color: var(--error);
        }
        button.danger:hover { background: rgba(248, 113, 113, 0.2); box-shadow: none; }

        .toggles { display: flex; gap: 1.25rem; margin-bottom: 1.25rem; }
        .toggle { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8125rem; color: var(--text-muted); cursor: pointer; }
        .toggle input { accent-color: var(--accent); }

        .results { display: flex; flex-direction: column; gap: 0.625rem; }
        .result-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1rem;
            transition: border-color 0.15s;
        }
        .result-card:hover { border-color: rgba(167,139,250,0.3); }
        .result-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; gap: 1rem; }
        .result-title { font-weight: 600; font-size: 0.8125rem; color: var(--accent); word-break: break-all; line-height: 1.4; }
        .result-meta { font-size: 0.7rem; color: var(--text-muted); text-align: right; white-space: nowrap; flex-shrink: 0; }
        .result-content {
            font-size: 0.8rem;
            color: var(--text-muted);
            white-space: pre-wrap;
            max-height: 180px;
            overflow-y: auto;
            background: var(--bg);
            padding: 0.625rem 0.75rem;
            border-radius: 6px;
            font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
            line-height: 1.5;
        }
        .result-tags { margin-top: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap; }
        .tag {
            background: var(--accent-dim);
            border: 1px solid rgba(167,139,250,0.2);
            padding: 0.1rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            color: var(--accent);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1rem 1.25rem;
        }
        .stat-label { font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.375rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-value { font-size: 1.75rem; font-weight: 700; }
        .stat-value.ok { color: var(--success); }
        .stat-value.error { color: var(--error); }

        .reindex-section { margin-top: 1.5rem; }
        .section-title { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.75rem; }
        .reindex-buttons { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
        .status-log {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 0.875rem 1rem;
            font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
            font-size: 0.75rem;
            max-height: 280px;
            overflow-y: auto;
            white-space: pre-wrap;
            color: var(--text-muted);
            line-height: 1.5;
        }
        .status-running { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }

        .repo-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.625rem 0.875rem;
            margin-bottom: 0.4rem;
            transition: border-color 0.15s;
        }
        .repo-item:hover { border-color: rgba(167,139,250,0.25); }
        .repo-name { font-size: 0.8125rem; font-family: 'SF Mono', Consolas, monospace; }
        .repo-actions { display: flex; gap: 0.4rem; flex-shrink: 0; }
        .add-repo-section { margin-top: 1.5rem; }
        .add-row { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }

        .message {
            padding: 0.625rem 0.875rem;
            border-radius: 8px;
            margin-bottom: 0.75rem;
            font-size: 0.8125rem;
        }
        .message.error { background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.2); color: var(--error); }
        .message.info { background: var(--accent-dim); border: 1px solid rgba(167,139,250,0.2); color: var(--accent); }

        .empty { color: var(--text-muted); font-style: italic; padding: 0.5rem 0; }
        .loading { opacity: 0.5; }
        a { color: var(--accent); text-decoration: none; }
        a:hover { text-decoration: underline; }

        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            __LOGO__
            <div class="header-text">
                <h1>Cortex</h1>
                <span>RAG Dashboard</span>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="search">Search</button>
            <button class="tab" data-tab="repos">Repos</button>
            <button class="tab" data-tab="admin">Admin</button>
        </div>

        <div id="search-panel" class="panel active">
            <form class="search-form" id="search-form">
                <input type="text" id="query" placeholder="Search notes and code..." autofocus>
                <button type="submit">Search</button>
            </form>
            <div class="toggles">
                <label class="toggle"><input type="checkbox" id="search-notes" checked><span>Notes</span></label>
                <label class="toggle"><input type="checkbox" id="search-code" checked><span>Code</span></label>
            </div>
            <div id="search-results" class="results"></div>
        </div>

        <div id="repos-panel" class="panel">
            <div id="repo-list"></div>
            <div class="add-repo-section">
                <div class="section-title">Add Repo</div>
                <div class="add-row">
                    <input type="text" id="repo-input" placeholder="Xoudusz/repo-name">
                    <button id="repo-add-btn">Add</button>
                </div>
                <button class="secondary" id="load-github-repos-btn">Load from GitHub</button>
                <div id="github-repo-picker" style="display:none;margin-top:0.75rem">
                    <select id="github-repo-select"><option value="">Select a repo...</option></select>
                    <button id="github-repo-add-btn">Add Selected</button>
                </div>
                <div id="repo-message" style="margin-top:0.75rem"></div>
            </div>
        </div>

        <div id="admin-panel" class="panel">
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-label">Notes indexed</div><div class="stat-value" id="stat-notes">—</div></div>
                <div class="stat-card"><div class="stat-label">Code chunks</div><div class="stat-value" id="stat-code">—</div></div>
                <div class="stat-card"><div class="stat-label">Ollama</div><div class="stat-value" id="stat-ollama">—</div></div>
            </div>
            <div class="reindex-section">
                <div class="section-title">Reindex</div>
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
        async function api(path, options = {}) {
            const res = await fetch(path, {
                ...options,
                headers: { 'Content-Type': 'application/json', ...options.headers }
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        }

        function escapeHtml(str) {
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab + '-panel').classList.add('active');
                if (tab.dataset.tab === 'admin') loadStats();
                if (tab.dataset.tab === 'repos') loadRepos();
            });
        });

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
            if (!collections.length) { resultsDiv.innerHTML = '<div class="message error">Select at least one collection</div>'; return; }
            resultsDiv.innerHTML = '<div class="empty loading">Searching...</div>';
            try {
                const data = await api('/api/search', { method: 'POST', body: JSON.stringify({ query, collections, limit: 10 }) });
                renderResults(data);
            } catch (err) {
                resultsDiv.innerHTML = '<div class="message error">' + escapeHtml(err.message) + '</div>';
            }
        });

        function renderResults(data) {
            const all = [
                ...(data.notes || []).map(r => ({ ...r, type: 'note' })),
                ...(data.code || []).map(r => ({ ...r, type: 'code' }))
            ].sort((a, b) => b.score - a.score);
            if (!all.length) { resultsDiv.innerHTML = '<div class="empty">No results found.</div>'; return; }
            resultsDiv.innerHTML = all.map(r => {
                if (r.type === 'note') {
                    const tags = (r.tags || []).map(t => '<span class="tag">' + escapeHtml(t) + '</span>').join('');
                    return '<div class="result-card"><div class="result-header"><div class="result-title">' + escapeHtml(r.file) + ' › ' + escapeHtml(r.heading) + '</div><div class="result-meta">score ' + r.score.toFixed(3) + '</div></div><div class="result-content">' + escapeHtml(r.text) + '</div>' + (tags ? '<div class="result-tags">' + tags + '</div>' : '') + '</div>';
                } else {
                    const link = r.github_url ? '<a href="' + escapeHtml(r.github_url) + '" target="_blank">↗ GitHub</a>' : '';
                    return '<div class="result-card"><div class="result-header"><div class="result-title">' + escapeHtml(r.repo) + ' / ' + escapeHtml(r.file) + ' :' + r.start_line + '-' + r.end_line + '</div><div class="result-meta">' + escapeHtml(r.language || '') + ' · ' + r.score.toFixed(3) + (link ? ' · ' + link : '') + '</div></div><div class="result-content">' + escapeHtml(r.text) + '</div></div>';
                }
            }).join('');
        }

        async function loadStats() {
            try {
                const data = await api('/api/stats');
                document.getElementById('stat-notes').textContent = data.notes?.points_count?.toLocaleString() ?? '—';
                document.getElementById('stat-code').textContent = data.code?.points_count?.toLocaleString() ?? '—';
                const ollama = document.getElementById('stat-ollama');
                ollama.textContent = data.ollama?.status === 'ok' ? '✓' : '✗';
                ollama.className = 'stat-value ' + (data.ollama?.status === 'ok' ? 'ok' : 'error');
            } catch (err) { console.error('Failed to load stats:', err); }
        }

        let statusPoll = null;
        document.getElementById('reindex-all').addEventListener('click', () => triggerReindex(true, true));
        document.getElementById('reindex-notes').addEventListener('click', () => triggerReindex(true, false));
        document.getElementById('reindex-code').addEventListener('click', () => triggerReindex(false, true));

        async function triggerReindex(notes, code, repo) {
            try {
                const data = await api('/api/reindex', { method: 'POST', body: JSON.stringify({ notes, code, repo: repo || '' }) });
                if (data.status === 'started' || data.status === 'already_running') pollStatus();
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
                    let text = 'Status: ' + (data.running ? 'running' : 'done') + ' (' + Math.round(data.elapsed_seconds) + 's)\n\n';
                    text += (data.output || []).join('\n');
                    if (data.error) text += '\n\nError: ' + data.error;
                    statusDiv.textContent = text;
                    statusDiv.scrollTop = statusDiv.scrollHeight;
                    if (data.done && !data.running) {
                        clearInterval(statusPoll); statusPoll = null;
                        statusDiv.classList.remove('status-running');
                        loadStats();
                    }
                } catch (err) { statusDiv.textContent = 'Error polling status: ' + err.message; }
            };
            await update();
            statusPoll = setInterval(update, 2000);
        }

        api('/api/status').then(data => {
            if (data.running) pollStatus();
            else if (data.done) {
                let text = 'Last run: done (' + Math.round(data.elapsed_seconds) + 's)\n\n';
                text += (data.output || []).join('\n');
                document.getElementById('reindex-status').textContent = text;
            }
        }).catch(() => {});

        async function loadRepos() {
            const listDiv = document.getElementById('repo-list');
            listDiv.innerHTML = '<div class="empty loading">Loading...</div>';
            try {
                const data = await api('/api/repos');
                renderRepos(data.repos || []);
            } catch (err) {
                listDiv.innerHTML = '<div class="message error">' + escapeHtml(err.message) + '</div>';
            }
        }

        function renderRepos(repos) {
            const listDiv = document.getElementById('repo-list');
            if (!repos.length) { listDiv.innerHTML = '<div class="empty">No repos configured.</div>'; return; }
            listDiv.innerHTML = repos.map(repo =>
                '<div class="repo-item" data-repo="' + escapeHtml(repo) + '"><span class="repo-name">' + escapeHtml(repo) + '</span><div class="repo-actions"><button class="secondary small repo-reindex-btn">Reindex</button><button class="danger small repo-remove-btn">Remove</button></div></div>'
            ).join('');
            listDiv.querySelectorAll('.repo-reindex-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const repo = btn.closest('.repo-item').dataset.repo;
                    const name = repo.split('/')[1];
                    btn.disabled = true; btn.textContent = '...';
                    try { await triggerReindex(false, true, name); showRepoMsg('Reindexing ' + name + '… check Admin tab.', 'info'); }
                    catch (err) { showRepoMsg(err.message, 'error'); }
                    finally { btn.disabled = false; btn.textContent = 'Reindex'; }
                });
            });
            listDiv.querySelectorAll('.repo-remove-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const repo = btn.closest('.repo-item').dataset.repo;
                    try {
                        const data = await api('/api/repos/' + encodeURIComponent(repo), { method: 'DELETE' });
                        renderRepos(data.repos || []); showRepoMsg('Removed ' + repo, 'info');
                    } catch (err) { showRepoMsg(err.message, 'error'); }
                });
            });
        }

        function showRepoMsg(msg, type) {
            const div = document.getElementById('repo-message');
            div.innerHTML = '<div class="message ' + type + '">' + escapeHtml(msg) + '</div>';
            setTimeout(() => { div.innerHTML = ''; }, 4000);
        }

        document.getElementById('repo-add-btn').addEventListener('click', async () => {
            const val = document.getElementById('repo-input').value.trim();
            if (!val) return;
            try {
                const data = await api('/api/repos', { method: 'POST', body: JSON.stringify({ repo: val }) });
                document.getElementById('repo-input').value = '';
                renderRepos(data.repos || []); showRepoMsg('Added ' + val, 'info');
            } catch (err) { showRepoMsg(err.message, 'error'); }
        });

        document.getElementById('repo-input').addEventListener('keydown', e => {
            if (e.key === 'Enter') document.getElementById('repo-add-btn').click();
        });

        document.getElementById('load-github-repos-btn').addEventListener('click', async () => {
            const btn = document.getElementById('load-github-repos-btn');
            btn.disabled = true; btn.textContent = 'Loading...';
            try {
                const data = await api('/api/github/repos');
                const select = document.getElementById('github-repo-select');
                select.innerHTML = '<option value="">Select a repo...</option>' +
                    (data.repos || []).map(r => '<option value="' + escapeHtml(r) + '">' + escapeHtml(r) + '</option>').join('');
                document.getElementById('github-repo-picker').style.display = 'block';
            } catch (err) { showRepoMsg(err.message, 'error'); }
            finally { btn.disabled = false; btn.textContent = 'Load from GitHub'; }
        });

        document.getElementById('github-repo-add-btn').addEventListener('click', async () => {
            const val = document.getElementById('github-repo-select').value;
            if (!val) return;
            try {
                const data = await api('/api/repos', { method: 'POST', body: JSON.stringify({ repo: val }) });
                renderRepos(data.repos || []); showRepoMsg('Added ' + val, 'info');
            } catch (err) { showRepoMsg(err.message, 'error'); }
        });
    </script>
</body>
</html>"""

UI_HTML = _UI_TEMPLATE.replace("__FAVICON__", FAVICON).replace("__LOGO__", LOGO_SVG)


async def ui(request: Request) -> HTMLResponse:
    return HTMLResponse(UI_HTML)


async def api_search(request: Request, qdrant_url: str, embed_fn) -> JSONResponse:
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
                {"file": p.payload.get("file", ""), "heading": p.payload.get("heading", ""),
                 "text": p.payload.get("text", ""), "tags": p.payload.get("tags", []), "score": round(p.score, 4)}
                for p in points
            ]
        except Exception as e:
            result["notes"] = []; result["notes_error"] = str(e)

    if "code" in collections:
        try:
            points = client.query_points("code", query=vector, limit=limit, with_payload=True).points
            result["code"] = [
                {"repo": p.payload.get("repo", ""), "file": p.payload.get("file", ""),
                 "start_line": p.payload.get("start_line", 0), "end_line": p.payload.get("end_line", 0),
                 "language": p.payload.get("language", ""), "text": p.payload.get("text", ""),
                 "github_url": p.payload.get("github_url", ""), "score": round(p.score, 4)}
                for p in points
            ]
        except Exception as e:
            result["code"] = []; result["code_error"] = str(e)

    return JSONResponse(result)


async def api_status(request: Request, reindex_state: dict) -> JSONResponse:
    import time
    s = reindex_state
    if s["started_at"] is None:
        return JSONResponse({"running": False, "elapsed_seconds": 0, "output": [], "error": None, "done": False})
    elapsed = time.time() - s["started_at"]
    return JSONResponse({"running": s["running"], "elapsed_seconds": round(elapsed, 1),
                         "output": s["output"][-100:], "error": s["error"], "done": s["done"]})


async def api_reindex(request: Request, reindex_lock, reindex_state: dict, run_reindex_fn) -> JSONResponse:
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
    return JSONResponse(result)
