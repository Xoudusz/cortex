"""Cortex Web UI — embedded HTML/CSS/JS template and SVG logo."""

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
    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg: #111318;
            --surface: #1c2030;
            --border: #2d3248;
            --text: #e2e8f0;
            --text-muted: #8896a8;
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
        .header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; padding-bottom: 1.25rem; border-bottom: 1px solid var(--border); }
        .logo-svg { width: 28px; height: 28px; flex-shrink: 0; }
        .header-text { flex: 1; }
        .header-text h1 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.01em; background: linear-gradient(135deg, #c084fc, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
        .header-text span { font-size: 0.75rem; color: var(--text-muted); }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); flex-shrink: 0; display: none; }
        .status-dot.active { display: block; animation: pulse-dot 1.2s ease-in-out infinite; }
        @keyframes pulse-dot { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.75); } }
        .tabs { display: flex; gap: 0.25rem; margin-bottom: 1.5rem; background: var(--surface); padding: 0.25rem; border-radius: 8px; width: fit-content; }
        .tab { background: transparent; border: none; color: var(--text-muted); padding: 0.4rem 1rem; cursor: pointer; border-radius: 6px; font-size: 0.8125rem; font-weight: 500; transition: all 0.15s; }
        .tab:hover { color: var(--text); }
        .tab.active { background: var(--accent-dim); color: var(--accent); box-shadow: inset 0 0 0 1px rgba(167,139,250,0.25); }
        .panel { display: none; }
        .panel.active { display: block; }
        .search-form { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
        input[type="text"] { flex: 1; padding: 0.625rem 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.875rem; transition: border-color 0.15s; }
        input[type="text"]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        input[type="text"]::placeholder { color: var(--text-muted); }
        select { padding: 0.5rem 0.75rem; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.8125rem; cursor: pointer; }
        select:focus { outline: none; border-color: var(--accent); }
        button { padding: 0.625rem 1.25rem; background: var(--accent); border: none; border-radius: 8px; color: #fff; cursor: pointer; font-size: 0.875rem; font-weight: 500; transition: all 0.15s; }
        button:hover { background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 4px 12px var(--accent-glow); }
        button:active { transform: translateY(0); }
        button:disabled { opacity: 0.45; cursor: not-allowed; transform: none; box-shadow: none; }
        button.secondary { background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); }
        button.secondary:hover { border-color: var(--accent); color: var(--accent); box-shadow: none; }
        button.small { padding: 0.3rem 0.7rem; font-size: 0.75rem; }
        button.danger { background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.3); color: var(--error); }
        button.danger:hover { background: rgba(248,113,113,0.2); box-shadow: none; }
        .toggles { display: flex; gap: 1.25rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
        .toggle { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8125rem; color: var(--text-muted); cursor: pointer; }
        .toggle input { accent-color: var(--accent); }
        .repo-filter-row { margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
        .repo-filter-label { font-size: 0.75rem; color: var(--text-muted); white-space: nowrap; }
        .results { display: flex; flex-direction: column; gap: 0.625rem; }
        .result-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; transition: border-color 0.15s; }
        .result-card:hover { border-color: rgba(167,139,250,0.3); }
        .result-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; gap: 1rem; }
        .result-title { font-weight: 600; font-size: 0.8125rem; color: var(--accent); word-break: break-all; line-height: 1.4; }
        .result-meta { font-size: 0.7rem; color: var(--text-muted); text-align: right; white-space: nowrap; flex-shrink: 0; }
        .result-content { font-size: 0.8rem; color: var(--text-muted); white-space: pre-wrap; max-height: 180px; overflow-y: auto; background: var(--bg); padding: 0.625rem 0.75rem; border-radius: 6px; font-family: 'SF Mono', 'Fira Code', Consolas, monospace; line-height: 1.5; }
        .result-tags { margin-top: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap; }
        .tag { background: var(--accent-dim); border: 1px solid rgba(167,139,250,0.2); padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 0.7rem; color: var(--accent); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.75rem; margin-bottom: 1.5rem; }
        .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.25rem; }
        .stat-label { font-size: 0.7rem; color: var(--text-muted); margin-bottom: 0.375rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-value { font-size: 1.75rem; font-weight: 700; }
        .stat-value.ok { color: var(--success); }
        .stat-value.error { color: var(--error); }
        .section { margin-top: 1.5rem; }
        .section-title { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.75rem; }
        .admin-tabs { display:flex; gap:0.2rem; margin-bottom:0; border-bottom:1px solid var(--border); }
        .admin-tab { background:transparent; border:none; border-bottom:2px solid transparent; color:var(--text-muted); padding:0.4rem 0.75rem; cursor:pointer; font-size:0.8rem; font-weight:500; transition:all 0.15s; margin-bottom:-1px; border-radius:0; }
        .admin-tab:hover { color:var(--text); transform:none; box-shadow:none; background:transparent; }
        .admin-tab.active { color:var(--accent); border-bottom-color:var(--accent); background:transparent; }
        .admin-section { display:none; padding-top:1rem; }
        .admin-section.active { display:block; }
        .reindex-buttons { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
        .status-log { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.875rem 1rem; font-family: 'SF Mono', 'Fira Code', Consolas, monospace; font-size: 0.75rem; max-height: 280px; overflow-y: auto; white-space: pre-wrap; color: var(--text-muted); line-height: 1.5; }
        .status-running { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
        .webhook-table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
        .webhook-table th { text-align: left; padding: 0.5rem 0.75rem; color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border); }
        .webhook-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(45,50,72,0.5); font-family: 'SF Mono', Consolas, monospace; }
        .webhook-table tr:last-child td { border-bottom: none; }
        .wh-triggered { color: var(--success); }
        .wh-done { color: var(--text-muted); }
        .wh-failed { color: #f87171; }
        .wh-skipped { color: var(--text-muted); }
        .repo-item { display: flex; justify-content: space-between; align-items: center; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.625rem 0.875rem; margin-bottom: 0.4rem; transition: border-color 0.15s; }
        .repo-item:hover { border-color: rgba(167,139,250,0.25); }
        .repo-item.indexed { border-color: rgba(167,139,250,0.2); }
        .repo-info { display: flex; align-items: center; gap: 0.5rem; min-width: 0; flex: 1; }
        .repo-name { font-size: 0.8125rem; font-family: 'SF Mono', Consolas, monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .repo-meta { display: flex; align-items: center; gap: 0.4rem; flex-shrink: 0; }
        .repo-badge { font-size: 0.65rem; background: var(--accent-dim); color: var(--accent); border: 1px solid rgba(167,139,250,0.3); padding: 0.1rem 0.4rem; border-radius: 4px; }
        .repo-age { font-size: 0.7rem; color: var(--text-muted); }
        .repo-actions { display: flex; gap: 0.4rem; flex-shrink: 0; margin-left: 0.75rem; }
        .message { padding: 0.625rem 0.875rem; border-radius: 8px; margin-bottom: 0.75rem; font-size: 0.8125rem; }
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
            <span id="status-dot" class="status-dot" title="Reindexing..."></span>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="search">Search</button>
            <button class="tab" data-tab="repos">Repos</button>
            <button class="tab" data-tab="admin">Admin</button>
            <button class="tab" data-tab="graph">Graph</button>
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
            <div class="repo-filter-row" id="repo-filter-row" style="display:none">
                <span class="repo-filter-label">Repo:</span>
                <select id="repo-filter"><option value="">All repos</option></select>
            </div>
            <div id="search-results" class="results"></div>
        </div>

        <div id="repos-panel" class="panel">
            <div id="repo-list"></div>
            <div id="repo-message" style="margin-top:0.75rem"></div>
        </div>

        <div id="admin-panel" class="panel">
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-label">Notes indexed</div><div class="stat-value" id="stat-notes">-</div></div>
                <div class="stat-card"><div class="stat-label">Code chunks</div><div class="stat-value" id="stat-code">-</div></div>
                <div class="stat-card"><div class="stat-label">Ollama</div><div class="stat-value" id="stat-ollama">-</div></div>
            </div>
            <div class="admin-tabs">
                <button class="admin-tab active" data-admin-tab="reindex">Reindex</button>
                <button class="admin-tab" data-admin-tab="graph">Graph Efficiency</button>
                <button class="admin-tab" data-admin-tab="webhooks">Webhooks</button>
                <button class="admin-tab" data-admin-tab="logs">Logs</button>
            </div>
            <div id="admin-reindex" class="admin-section active">
                <div class="reindex-buttons">
                    <button id="reindex-all">Reindex All</button>
                    <button id="reindex-notes" class="secondary">Notes Only</button>
                    <button id="reindex-code" class="secondary">Code Only</button>
                </div>
                <div style="margin:0.5rem 0 0.75rem;display:flex;align-items:center;gap:0.75rem">
                    <label style="display:flex;align-items:center;gap:0.4rem;font-size:0.82rem;color:var(--text-muted);cursor:pointer">
                        <input type="checkbox" id="force-reindex" style="cursor:pointer">
                        Force re-embed (clear cache)
                    </label>
                    <button id="clear-cache-btn" class="secondary" style="font-size:0.8rem;padding:0.25rem 0.6rem;color:var(--text-muted)">Clear Cache Only</button>
                </div>
                <div id="queue-list" style="display:none;font-size:0.78rem;color:var(--text-muted);margin-bottom:0.5rem;padding:0.3rem 0.5rem;background:var(--accent-dim);border-radius:4px"></div>
                <div id="reindex-status" class="status-log">No reindex running.</div>
                <div style="margin-top:1.25rem"><div class="section-title">Job History</div><div id="reindex-log-wrap"><div class="empty">No jobs run yet.</div></div></div>
            </div>
            <div id="admin-graph" class="admin-section">
                <table class="webhook-table"><tbody id="graph-stats-body"><tr><td colspan="2" class="empty">Click Graph Efficiency to load.</td></tr></tbody></table>
                <div style="margin-top:0.5rem;text-align:right"><button id="history-btn" style="display:none;background:none;border:1px solid var(--border);color:var(--text-muted);border-radius:6px;padding:0.3rem 0.75rem;font-size:0.8rem;cursor:pointer">Show past versions</button></div>
            </div>
            <div id="admin-webhooks" class="admin-section">
                <div id="webhook-log-wrap"><div class="empty">No webhooks received yet.</div></div>
            </div>
            <div id="admin-logs" class="admin-section">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem"><span style="font-size:0.75rem;color:var(--text-muted)">Last 200 lines</span><div style="display:flex;gap:0.5rem;align-items:center"><label style="font-size:0.75rem;color:var(--text-muted);cursor:pointer"><input type="checkbox" id="log-tail-toggle" style="margin-right:0.25rem">tail</label><button onclick="loadLogs()" class="secondary" style="padding:0.2rem 0.6rem;font-size:0.75rem">Refresh</button></div></div>
                <pre id="log-output" style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:0.75rem;font-size:0.7rem;max-height:300px;overflow-y:auto;color:var(--text-muted);white-space:pre-wrap;word-break:break-all">No logs loaded.</pre>
            </div>
        </div>

        <div id="graph-panel" class="panel">
            <div style="display:flex;gap:0.5rem;margin-bottom:0.75rem;align-items:center">
                <select id="graph-repo-select" style="flex:1"><option value="notes">Notes (wikilinks)</option><option value="global">★ Global (cross-repo)</option></select>
                <button id="graph-load-btn" class="secondary" style="flex-shrink:0">Load Graph</button>
            </div>
            <div id="graph-info" style="font-size:0.75rem;color:var(--text-muted);margin-bottom:0.5rem;min-height:1.2em"></div>
            <div id="graph-container" style="width:100%;height:520px;background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;position:relative">
                <svg id="graph-svg" style="width:100%;height:100%"></svg>
                <div id="graph-placeholder" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:0.875rem;pointer-events:none">Select a repo and click Load Graph</div>
            </div>
            <div id="graph-detail" style="margin-top:0.75rem"></div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
    <script>
        const NL = String.fromCharCode(10);

        function getToken() { return localStorage.getItem('cortex_token') || ''; }

        function generateVerifier() {
            const arr = new Uint8Array(32);
            crypto.getRandomValues(arr);
            return btoa(String.fromCharCode(...arr)).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
        }

        function startOAuthFlow() {
            const verifier = generateVerifier();
            localStorage.setItem('cortex_pkce_verifier', verifier);
            crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)).then(hash => {
                const challenge = btoa(String.fromCharCode(...new Uint8Array(hash)))
                    .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
                const redirectUri = window.location.origin + '/';
                const params = new URLSearchParams({
                    response_type: 'code',
                    client_id: 'cortex-web-ui',
                    redirect_uri: redirectUri,
                    code_challenge: challenge,
                    code_challenge_method: 'S256',
                });
                window.location.href = '/oauth/authorize?' + params.toString();
            });
        }

        (async function initAuth() {
            const params = new URLSearchParams(window.location.search);
            const code = params.get('code');
            if (code) {
                const verifier = localStorage.getItem('cortex_pkce_verifier');
                if (verifier) {
                    try {
                        const res = await fetch('/token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                            body: new URLSearchParams({
                                grant_type: 'authorization_code',
                                code,
                                code_verifier: verifier,
                                client_id: 'cortex-web-ui',
                                redirect_uri: window.location.origin + '/',
                            }),
                        });
                        if (res.ok) {
                            const data = await res.json();
                            localStorage.setItem('cortex_token', data.access_token);
                            if (data.refresh_token) localStorage.setItem('cortex_refresh', data.refresh_token);
                            localStorage.removeItem('cortex_pkce_verifier');
                        }
                    } catch (_) {}
                }
                history.replaceState({}, '', '/');
                window.location.reload();
                return;
            }
            if (!getToken()) startOAuthFlow();
        })();

        async function api(path, options = {}) {
            const token = getToken();
            const headers = { 'Content-Type': 'application/json', ...options.headers };
            if (token) headers['Authorization'] = 'Bearer ' + token;
            const res = await fetch(path, { ...options, headers });
            if (res.status === 401) { localStorage.removeItem('cortex_token'); startOAuthFlow(); return; }
            if (!res.ok) { const err = await res.json().catch(() => ({ error: res.statusText })); throw new Error(err.error || res.statusText); }
            return res.json();
        }

        function escapeHtml(str) {
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function timeAgo(iso) {
            if (!iso) return '';
            const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
            if (diff < 60) return 'just now';
            if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
            return Math.floor(diff / 86400) + 'd ago';
        }

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.tab + '-panel').classList.add('active');
                if (tab.dataset.tab === 'admin') { loadStats(); loadReindexLog(); }
                if (tab.dataset.tab === 'repos') loadRepos();
                if (tab.dataset.tab === 'graph') loadGraphRepos();
            });
        });
        document.querySelectorAll('.admin-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById('admin-' + tab.dataset.adminTab).classList.add('active');
                if (tab.dataset.adminTab === 'reindex') loadReindexLog();
                if (tab.dataset.adminTab === 'graph') loadStats();
                if (tab.dataset.adminTab === 'webhooks') loadWebhookLog();
                if (tab.dataset.adminTab === 'logs') loadLogs();
            });
        });

        const statusDot = document.getElementById('status-dot');
        async function pollStatusDot() { try { const data = await api('/api/status'); statusDot.classList.toggle('active', !!data.running); if ((data.running || (data.queue && data.queue.length)) && !statusPoll) pollStatus(); } catch (_) {} }
        pollStatusDot();
        setInterval(pollStatusDot, 5000);

        const searchForm = document.getElementById('search-form');
        const queryInput = document.getElementById('query');
        const resultsDiv = document.getElementById('search-results');
        const codeToggle = document.getElementById('search-code');
        const repoFilterRow = document.getElementById('repo-filter-row');
        const repoFilterSelect = document.getElementById('repo-filter');

        function updateRepoFilterVisibility() { repoFilterRow.style.display = codeToggle.checked ? 'flex' : 'none'; }
        codeToggle.addEventListener('change', updateRepoFilterVisibility);

        async function loadRepoFilter() {
            try {
                const meta = await api('/api/repos-meta');
                const indexed = (meta.indexed_at ? Object.keys(meta.indexed_at) : (meta.repos || []).map(r => r.split('/')[1]));
                repoFilterSelect.innerHTML = '<option value="">All repos</option>' + indexed.map(n => '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>').join('');
            } catch (_) {}
        }
        loadRepoFilter();

        searchForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const query = queryInput.value.trim();
            if (!query) return;
            const collections = [];
            if (document.getElementById('search-notes').checked) collections.push('notes');
            if (codeToggle.checked) collections.push('code');
            if (!collections.length) { resultsDiv.innerHTML = '<div class="message error">Select at least one collection</div>'; return; }
            const repoFilter = repoFilterSelect.value;
            resultsDiv.innerHTML = '<div class="empty loading">Searching...</div>';
            try {
                const body = { query, collections, limit: 10 };
                if (repoFilter) body.repo = repoFilter;
                const data = await api('/api/search', { method: 'POST', body: JSON.stringify(body) });
                renderResults(data);
            } catch (err) { resultsDiv.innerHTML = '<div class="message error">' + escapeHtml(err.message) + '</div>'; }
        });

        function renderResults(data) {
            const all = [...(data.notes || []).map(r => ({ ...r, type: 'note' })), ...(data.code || []).map(r => ({ ...r, type: 'code' }))].sort((a, b) => b.score - a.score);
            if (!all.length) { resultsDiv.innerHTML = '<div class="empty">No results found.</div>'; return; }
            resultsDiv.innerHTML = all.map(r => {
                if (r.type === 'note') {
                    const tags = (r.tags || []).map(t => '<span class="tag">' + escapeHtml(t) + '</span>').join('');
                    return '<div class="result-card"><div class="result-header"><div class="result-title">' + escapeHtml(r.file) + ' > ' + escapeHtml(r.heading) + '</div><div class="result-meta">score ' + r.score.toFixed(3) + '</div></div><div class="result-content">' + escapeHtml(r.text) + '</div>' + (tags ? '<div class="result-tags">' + tags + '</div>' : '') + '</div>';
                } else {
                    const link = r.github_url ? '<a href="' + escapeHtml(r.github_url) + '" target="_blank">GitHub</a>' : '';
                    return '<div class="result-card"><div class="result-header"><div class="result-title">' + escapeHtml(r.repo) + ' / ' + escapeHtml(r.file) + ' :' + r.start_line + '-' + r.end_line + '</div><div class="result-meta">' + escapeHtml(r.language || '') + ' · ' + r.score.toFixed(3) + (link ? ' · ' + link : '') + '</div></div><div class="result-content">' + escapeHtml(r.text) + '</div></div>';
                }
            }).join('');
        }

        async function loadStats() {
            try {
                const data = await api('/api/stats');
                document.getElementById('stat-notes').textContent = data.notes?.points_count?.toLocaleString() ?? '-';
                document.getElementById('stat-code').textContent = data.code?.points_count?.toLocaleString() ?? '-';
                const ollama = document.getElementById('stat-ollama');
                ollama.textContent = data.ollama?.status === 'ok' ? '✓' : '✗';
                ollama.className = 'stat-value ' + (data.ollama?.status === 'ok' ? 'ok' : 'error');
                if (data.graph) {
                    const g = data.graph;
                    const avgLift = g.centrality_lift_count > 0 ? (g.centrality_lift_total / g.centrality_lift_count).toFixed(4) : '—';
                    const pprRate = g.search_notes_calls > 0 ? ((g.ppr_fires / g.search_notes_calls) * 100).toFixed(1) + '%' : '—';
                    const total = g.graph_cache_hits + g.graph_cache_misses;
                    const cacheRate = total > 0 ? ((g.graph_cache_hits / total) * 100).toFixed(1) + '%' : '—';
                    const rows = [
                        ['version', '<span class="repo-badge">' + escapeHtml(g.version || '?') + '</span>'],
                        ['started', g.started_at ? new Date(g.started_at).toLocaleString() : '—'],
                        ['search_code calls', g.search_code_calls],
                        ['centrality lift avg', avgLift + ' (across ' + g.centrality_lift_count + ' results)'],
                        ['search_notes calls', g.search_notes_calls],
                        ['PPR fires', g.ppr_fires + ' (' + pprRate + ' of calls)'],
                        ['PPR results added', g.ppr_results_added],
                        ['graph cache hit rate', cacheRate + ' (' + g.graph_cache_hits + '/' + total + ')'],
                        ['embed cache skipped', 'notes=' + (g.embed_cache_notes || 0) + '  code=' + (g.embed_cache_code || 0)],
                        ['context injected', (((g.context_tokens_notes||0) + (g.context_tokens_code||0)) / 1000).toFixed(1) + 'k tokens  (notes=' + Math.round((g.context_tokens_notes||0)/1000) + 'k  code=' + Math.round((g.context_tokens_code||0)/1000) + 'k)'],
                    ];
                    let html = rows.map(([k, v]) => '<tr><td style="color:var(--text-muted);width:55%">' + escapeHtml(String(k)) + '</td><td>' + v + '</td></tr>').join('');
                    document.getElementById('graph-stats-body').innerHTML = html;
                    const hist = g.history || {};
                    const histKeys = Object.keys(hist).sort((a,b)=>{ const p=v=>v.split('.').map(Number); const [a1,a2,a3]=(p(a)||[0,0,0]); const [b1,b2,b3]=(p(b)||[0,0,0]); return b1-a1||b2-a2||b3-a3; });
                    const btn = document.getElementById('history-btn');
                    if (histKeys.length) {
                        btn.style.display = '';
                        btn.textContent = 'Show past versions (' + histKeys.length + ')';
                        btn.onclick = () => openHistoryModal(hist, histKeys);
                    } else {
                        btn.style.display = 'none';
                    }
                }
            } catch (err) { console.error('Failed to load stats:', err); }
        }

        async function loadWebhookLog() {
            const wrap = document.getElementById('webhook-log-wrap');
            try {
                const data = await api('/api/webhook-log');
                const log = data.log || [];
                if (!log.length) { wrap.innerHTML = '<div class="empty">No webhooks received yet.</div>'; return; }
                wrap.innerHTML = '<table class="webhook-table"><thead><tr><th>Repo</th><th>Time</th><th>Status</th></tr></thead><tbody>' + log.map(e => '<tr><td>' + escapeHtml(e.repo) + '</td><td>' + timeAgo(e.ts) + '</td><td class="' + (e.status === 'triggered' || e.status === 'merged' ? 'wh-triggered' : e.status === 'done' ? 'wh-done' : e.status === 'failed' ? 'wh-failed' : 'wh-skipped') + '">' + escapeHtml(e.status) + '</td></tr>').join('') + '</tbody></table>';
            } catch (err) { wrap.innerHTML = '<div class="empty">Failed to load webhook log.</div>'; }
        }

        async function loadReindexLog() {
            const wrap = document.getElementById('reindex-log-wrap');
            try {
                const data = await api('/api/reindex-log');
                const log = data.log || [];
                if (!log.length) { wrap.innerHTML = '<div class="empty">No jobs run yet.</div>'; return; }
                wrap.innerHTML = '<table class="webhook-table"><thead><tr><th>Type</th><th>Mode</th><th>Time</th><th>Duration</th><th>Status</th></tr></thead><tbody>' +
                    log.map(e => '<tr><td>' + escapeHtml(e.type) + '</td><td style="color:var(--text-muted)">' + escapeHtml(e.mode) + '</td><td>' + timeAgo(e.ts) + '</td><td style="color:var(--text-muted)">' + e.duration + 's</td><td class="' + (e.status === 'done' ? 'wh-done' : 'wh-failed') + '">' + escapeHtml(e.status) + (e.error ? ' — ' + escapeHtml(e.error.slice(0,40)) : '') + '</td></tr>').join('') + '</tbody></table>';
            } catch (err) { wrap.innerHTML = '<div class="empty">Failed to load job history.</div>'; }
        }

        let _logTailInterval = null;
        async function loadLogs() {
            const pre = document.getElementById('log-output');
            try {
                const data = await api('/api/logs?lines=200');
                pre.textContent = data.lines.length ? data.lines.join('\\n') : 'Log file empty.';
                pre.scrollTop = pre.scrollHeight;
            } catch (err) { pre.textContent = 'Failed to load logs.'; }
        }
        document.getElementById('log-tail-toggle').addEventListener('change', function() {
            if (this.checked) { loadLogs(); _logTailInterval = setInterval(loadLogs, 5000); }
            else { clearInterval(_logTailInterval); _logTailInterval = null; }
        });

        let statusPoll = null;
        document.getElementById('reindex-all').addEventListener('click', function() { triggerReindex(true, true, '', this); });
        document.getElementById('reindex-notes').addEventListener('click', function() { triggerReindex(true, false, '', this); });
        document.getElementById('reindex-code').addEventListener('click', function() { triggerReindex(false, true, '', this); });

        async function triggerReindex(notes, code, repo, btn) {
            const force = document.getElementById('force-reindex').checked;
            if (btn) { btn.disabled = true; btn._origText = btn.textContent; btn.textContent += force ? ' (force queued)' : ' (queued)'; }
            try {
                await api('/api/reindex', { method: 'POST', body: JSON.stringify({ notes, code, repo: repo || '', force }) });
                pollStatus();
            } catch (err) {
                document.getElementById('reindex-status').textContent = 'Error: ' + err.message;
                if (btn) { btn.disabled = false; btn.textContent = btn._origText; }
            }
        }

        document.getElementById('clear-cache-btn').addEventListener('click', async function() {
            const btn = this;
            btn.disabled = true; btn._origText = btn.textContent; btn.textContent = 'Clearing...';
            try {
                const data = await api('/api/clear-cache', { method: 'POST', body: JSON.stringify({ all_workspaces: false }) });
                document.getElementById('reindex-status').textContent = `Cache cleared (${data.deleted} file(s) deleted). Run reindex to rebuild.`;
            } catch (err) {
                document.getElementById('reindex-status').textContent = 'Error: ' + err.message;
            } finally {
                btn.disabled = false; btn.textContent = btn._origText;
            }
        });

        function jobLabel(j) {
            if (!j) return '';
            if (j.notes && j.code) return j.repo ? 'All (' + j.repo + ')' : 'All';
            if (j.notes) return 'Notes';
            if (j.code) return j.repo ? 'Code (' + j.repo + ')' : 'Code';
            return '?';
        }

        function updateQueueDisplay(currentJob, queue) {
            const el = document.getElementById('queue-list');
            const parts = [];
            if (currentJob) parts.push('Running: ' + jobLabel(currentJob));
            if (queue && queue.length) parts.push('Queued: ' + queue.map(jobLabel).join(' → '));
            if (!parts.length) { el.style.display = 'none'; return; }
            el.textContent = parts.join('  |  ');
            el.style.display = '';
        }

        function syncButtonStates(currentJob, queue) {
            const all = document.getElementById('reindex-all');
            const notes = document.getElementById('reindex-notes');
            const code = document.getElementById('reindex-code');
            const activeJobs = [...(currentJob ? [currentJob] : []), ...(queue || [])];
            const notesActive = activeJobs.some(j => j.notes);
            const codeActive = activeJobs.some(j => j.code);
            [all, notes, code].forEach(b => { b.disabled = false; if (b._origText) { b.textContent = b._origText; delete b._origText; } });
            if (notesActive && codeActive) { all.disabled = true; }
            if (notesActive) { notes.disabled = true; }
            if (codeActive) { code.disabled = true; }
        }

        async function pollStatus() {
            if (statusPoll) clearInterval(statusPoll);
            const statusDiv = document.getElementById('reindex-status');
            statusDiv.classList.add('status-running');
            const update = async () => {
                try {
                    const data = await api('/api/status');
                    let text = 'Status: ' + (data.running ? 'running' : 'done') + ' (' + Math.round(data.elapsed_seconds) + 's)' + NL + NL;
                    text += (data.output || []).join(NL);
                    if (data.error) text += NL + NL + 'Error: ' + data.error;
                    statusDiv.textContent = text;
                    statusDiv.scrollTop = statusDiv.scrollHeight;
                    statusDot.classList.toggle('active', !!data.running);
                    updateQueueDisplay(data.current_job, data.queue);
                    syncButtonStates(data.current_job, data.queue);
                    if (data.done && !data.running && !(data.queue && data.queue.length)) {
                        clearInterval(statusPoll); statusPoll = null; statusDiv.classList.remove('status-running'); loadStats(); loadRepoFilter(); loadReindexLog();
                    }
                } catch (err) { statusDiv.textContent = 'Error polling status: ' + err.message; }
            };
            await update();
            statusPoll = setInterval(update, 2000);
        }

        api('/api/status').then(data => {
            updateQueueDisplay(data.queue);
            syncButtonStates(data.running, data.queue);
            if (data.running || (data.queue && data.queue.length)) pollStatus();
            else if (data.done) { let text = 'Last run: done (' + Math.round(data.elapsed_seconds) + 's)' + NL + NL; text += (data.output || []).join(NL); document.getElementById('reindex-status').textContent = text; }
        }).catch(() => {});

        async function loadRepos() {
            const listDiv = document.getElementById('repo-list');
            listDiv.innerHTML = '<div class="empty loading">Loading repos...</div>';
            try {
                const [metaRes, ghRes] = await Promise.allSettled([api('/api/repos-meta'), api('/api/github/repos')]);
                const meta = metaRes.status === 'fulfilled' ? metaRes.value : { repos: [], indexed_at: {} };
                const indexedList = meta.repos || [];
                const indexedAt = meta.indexed_at || {};
                const ghRepos = ghRes.status === 'fulfilled' ? (ghRes.value.repos || []) : indexedList;
                renderRepos(ghRepos, indexedList, indexedAt);
            } catch (err) { listDiv.innerHTML = '<div class="message error">' + escapeHtml(err.message) + '</div>'; }
        }

        function renderRepos(allRepos, indexedList, indexedAt) {
            const listDiv = document.getElementById('repo-list');
            if (!allRepos.length) { listDiv.innerHTML = '<div class="empty">No repos found.</div>'; return; }
            const indexedSet = new Set(indexedList);
            const sorted = [...allRepos].sort((a, b) => { const ai = indexedSet.has(a) ? 0 : 1; const bi = indexedSet.has(b) ? 0 : 1; return ai - bi || a.localeCompare(b); });
            listDiv.innerHTML = sorted.map(repo => {
                const isTracked = indexedSet.has(repo);
                const name = repo.split('/')[1];
                const hasIndexedAt = isTracked && !!indexedAt[name];
                const age = hasIndexedAt ? timeAgo(indexedAt[name]) : '';
                return '<div class="repo-item' + (hasIndexedAt ? ' indexed' : '') + '" data-repo="' + escapeHtml(repo) + '"><div class="repo-info"><span class="repo-name">' + escapeHtml(repo) + '</span>' + (hasIndexedAt ? '<div class="repo-meta"><span class="repo-badge">indexed</span><span class="repo-age">' + escapeHtml(age) + '</span></div>' : '') + '</div><div class="repo-actions">' + (isTracked ? '<button class="secondary small repo-reindex-btn">Reindex</button><button class="danger small repo-remove-btn">Remove</button>' : '<button class="secondary small repo-add-btn">Add to index</button>') + '</div></div>';
            }).join('');
            listDiv.querySelectorAll('.repo-reindex-btn').forEach(btn => { btn.addEventListener('click', async () => { const repo = btn.closest('.repo-item').dataset.repo; const name = repo.split('/')[1]; btn.disabled = true; btn.textContent = '...'; try { await triggerReindex(false, true, name); showRepoMsg('Reindexing ' + name + '...', 'info'); } catch (err) { showRepoMsg(err.message, 'error'); } finally { btn.disabled = false; btn.textContent = 'Reindex'; } }); });
            listDiv.querySelectorAll('.repo-remove-btn').forEach(btn => { btn.addEventListener('click', async () => { const repo = btn.closest('.repo-item').dataset.repo; try { const data = await api('/api/repos/' + encodeURIComponent(repo), { method: 'DELETE' }); renderRepos(allRepos, data.repos || [], indexedAt); showRepoMsg('Removed ' + repo.split('/')[1] + ' from index', 'info'); loadRepoFilter(); } catch (err) { showRepoMsg(err.message, 'error'); } }); });
            listDiv.querySelectorAll('.repo-add-btn').forEach(btn => { btn.addEventListener('click', async () => { const repo = btn.closest('.repo-item').dataset.repo; btn.disabled = true; btn.textContent = '...'; try { const data = await api('/api/repos', { method: 'POST', body: JSON.stringify({ repo }) }); renderRepos(allRepos, data.repos || [], indexedAt); const name = repo.split('/')[1]; showRepoMsg('Added ' + name + ' — indexing...', 'info'); await triggerReindex(false, true, name); loadRepoFilter(); } catch (err) { showRepoMsg(err.message, 'error'); btn.disabled = false; btn.textContent = 'Add to index'; } }); });
        }

        function showRepoMsg(msg, type) {
            const div = document.getElementById('repo-message');
            div.innerHTML = '<div class="message ' + type + '">' + escapeHtml(msg) + '</div>';
            setTimeout(() => { div.innerHTML = ''; }, 4000);
        }

        const GRAPH_COLORS = ['#a78bfa','#34d399','#f87171','#fbbf24','#60a5fa','#f472b6','#4ade80','#fb923c','#38bdf8','#e879f9'];
        let _sim = null;

        async function loadGraphRepos() {
            const sel = document.getElementById('graph-repo-select');
            if (sel.options.length > 2) return;
            try {
                const meta = await api('/api/repos-meta');
                (meta.repos || []).forEach(r => {
                    const n = r.split('/')[1];
                    const opt = document.createElement('option');
                    opt.value = n; opt.textContent = n;
                    sel.appendChild(opt);
                });
            } catch (_) {}
        }

        document.getElementById('graph-load-btn').addEventListener('click', async () => {
            const repo = document.getElementById('graph-repo-select').value;
            const info = document.getElementById('graph-info');
            const ph = document.getElementById('graph-placeholder');
            const detail = document.getElementById('graph-detail');
            info.textContent = 'Loading...';
            ph.style.display = 'flex'; ph.textContent = 'Loading...';
            detail.innerHTML = '';
            if (_sim) { _sim.stop(); _sim = null; }
            document.getElementById('graph-svg').innerHTML = '';
            try {
                const data = await api('/api/graph/' + encodeURIComponent(repo));
                ph.style.display = 'none';
                if (repo === 'global') {
                    renderGlobalGraph(data);
                    info.textContent = data.nodes.length + ' repos \xb7 ' + data.edges.length + ' cross-repo edges';
                } else {
                    renderGraph(data);
                    info.textContent = data.nodes.length + ' nodes \xb7 ' + data.edges.length + ' edges \xb7 ' + repo;
                    info.innerHTML += ' \xa0<span style=\"font-size:0.7rem;color:var(--text-muted)\"><span style=\"color:#4a6080\">&#9646;</span> import \xa0<span style=\"color:#7c3210\">&#9646;</span> call \xa0<span style=\"color:#1a5c3a\">&#9646;</span> inherits</span>';
                }
            } catch (err) {
                info.textContent = 'Error: ' + err.message;
                ph.textContent = err.message;
            }
        });

        function renderGraph(data) {
            const container = document.getElementById('graph-container');
            const W = container.clientWidth || 840;
            const H = container.clientHeight || 520;
            const svg = d3.select('#graph-svg');
            svg.selectAll('*').remove();
            const maxC = Math.max(...data.nodes.map(n => n.centrality || 0), 0.001);
            const r = d => 4 + 10 * ((d.centrality || 0) / maxC);
            const g = svg.append('g');
            svg.call(d3.zoom().scaleExtent([0.1, 8]).on('zoom', e => g.attr('transform', e.transform)));
            const defs=svg.append('defs');[['arr-import','#3d4466'],['arr-call','#7c3210'],['arr-inherits','#1a5c3a']].forEach(([id,color])=>{defs.append('marker').attr('id',id).attr('viewBox','0 -4 8 8').attr('refX',16).attr('refY',0).attr('markerWidth',5).attr('markerHeight',5).attr('orient','auto').append('path').attr('d','M0,-4L8,0L0,4').attr('fill',color);});
            const EDGE_COLOR={'import':'#2d3248','call':'#7c3210','inherits':'#1a5c3a'};const EDGE_MARKER={'import':'url(#arr-import)','call':'url(#arr-call)','inherits':'url(#arr-inherits)'};const link=g.append('g').selectAll('line').data(data.edges).join('line').attr('stroke',d=>EDGE_COLOR[d.type]||EDGE_COLOR.import).attr('stroke-width',d=>d.type==='inherits'?1.5:1).attr('marker-end',d=>EDGE_MARKER[d.type]||EDGE_MARKER.import).attr('opacity',0.6);
            const node = g.append('g').selectAll('g').data(data.nodes).join('g').attr('cursor','pointer')
                .call(d3.drag()
                    .on('start',(e,d)=>{ if(!e.active) _sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
                    .on('drag',(e,d)=>{ d.fx=e.x; d.fy=e.y; })
                    .on('end',(e,d)=>{ if(!e.active) _sim.alphaTarget(0); d.fx=null; d.fy=null; }))
                .on('click',(e,d)=>{
                    const id = d.id || d.file || '';
                    const imps = (d.imports||[]).slice(0,8).join(', ')||'—';
                    const iby = (d.imported_by||[]).slice(0,8).join(', ')||'—';
                    document.getElementById('graph-detail').innerHTML =
                        '<div class="result-card"><div class="result-title">' + escapeHtml(id) + '</div>' +
                        '<div style="margin-top:0.5rem;font-size:0.75rem;color:var(--text-muted)">' +
                        '<b>centrality:</b> ' + (d.centrality!=null?d.centrality.toFixed(4):'—') +
                        ' &nbsp;\xb7&nbsp; <b>community:</b> ' + (d.community_id!=null?d.community_id:'—') + '<br>' +
                        '<b>imports:</b> ' + escapeHtml(imps) + '<br><b>imported by:</b> ' + escapeHtml(iby) + '</div></div>';
                    e.stopPropagation();
                });
            node.append('circle').attr('r',r).attr('fill',d=>GRAPH_COLORS[(d.community_id||0)%GRAPH_COLORS.length]).attr('stroke','var(--bg)').attr('stroke-width',1.5).attr('opacity',0.88);
            node.append('text').text(d=>{ const id=d.id||d.file||''; return id.split('/').pop().replace(/\\.(ts|tsx|js|jsx|py|kt|kts|svelte)$/,''); }).attr('font-size','8px').attr('fill','#8896a8').attr('text-anchor','middle').attr('dy',d=>r(d)+9).style('pointer-events','none').style('user-select','none');
            container.addEventListener('click',()=>{ document.getElementById('graph-detail').innerHTML=''; });
            _sim = d3.forceSimulation(data.nodes)
                .force('link',d3.forceLink(data.edges).id(d=>d.id||d.file).distance(70).strength(0.4))
                .force('charge',d3.forceManyBody().strength(-100))
                .force('center',d3.forceCenter(W/2,H/2))
                .force('collide',d3.forceCollide().radius(d=>r(d)+5))
                .on('tick',()=>{
                    link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
                    node.attr('transform',d=>'translate('+d.x+','+d.y+')');
                });
        }

        function renderGlobalGraph(data) {
            const container = document.getElementById('graph-container');
            const W = container.clientWidth || 840;
            const H = container.clientHeight || 520;
            const svg = d3.select('#graph-svg');
            svg.selectAll('*').remove();
            const g = svg.append('g');
            svg.call(d3.zoom().scaleExtent([0.1,8]).on('zoom', e => g.attr('transform', e.transform)));
            const defs = svg.append('defs');
            defs.append('marker').attr('id','arr-cross').attr('viewBox','0 -4 8 8').attr('refX',32).attr('refY',0)
                .attr('markerWidth',5).attr('markerHeight',5).attr('orient','auto')
                .append('path').attr('d','M0,-4L8,0L0,4').attr('fill','#4a5568');
            const link = g.append('g').selectAll('line').data(data.edges).join('line')
                .attr('stroke','#4a5568').attr('stroke-width',1.5).attr('stroke-dasharray','5,3')
                .attr('marker-end','url(#arr-cross)').attr('opacity',0.7);
            const REPO_COLORS = ['#a78bfa','#34d399','#f87171','#fbbf24','#60a5fa','#f472b6','#4ade80','#fb923c'];
            const colorMap = {};
            data.nodes.forEach((n,i) => { colorMap[n.id] = REPO_COLORS[i % REPO_COLORS.length]; });
            const node = g.append('g').selectAll('g').data(data.nodes).join('g')
                .attr('cursor','pointer')
                .call(d3.drag()
                    .on('start',(e,d)=>{ if(!e.active) _sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
                    .on('drag',(e,d)=>{ d.fx=e.x; d.fy=e.y; })
                    .on('end',(e,d)=>{ if(!e.active) _sim.alphaTarget(0); d.fx=null; d.fy=null; }))
                .on('click',(e,d)=>{
                    const incoming = data.edges.filter(ed => (ed.target?.id||ed.target) === d.id);
                    const outgoing = data.edges.filter(ed => (ed.source?.id||ed.source) === d.id);
                    let html = '<div class=\"result-card\"><div class=\"result-title\">' + escapeHtml(d.id) + '</div>';
                    html += '<div style=\"margin-top:0.5rem;font-size:0.75rem;color:var(--text-muted)\">';
                    if (outgoing.length) { html += '<b>references:</b><br>' + outgoing.map(ed => { const t=ed.target?.id||ed.target; return '  → '+escapeHtml(t)+(ed.files?.length?' via '+escapeHtml(ed.files.slice(0,3).join(', ')):'')+NL; }).join('<br>'); }
                    if (incoming.length) { html += '<b>referenced by:</b><br>' + incoming.map(ed => { const s=ed.source?.id||ed.source; return '  ← '+escapeHtml(s)+(ed.files?.length?' via '+escapeHtml(ed.files.slice(0,3).join(', ')):'')+NL; }).join('<br>'); }
                    if (!outgoing.length && !incoming.length) html += '(no cross-repo connections)';
                    html += '</div></div>';
                    document.getElementById('graph-detail').innerHTML = html;
                    e.stopPropagation();
                });
            node.append('circle').attr('r',20).attr('fill',d=>colorMap[d.id]).attr('stroke','var(--bg)').attr('stroke-width',2).attr('opacity',0.9);
            node.append('text').text(d=>d.id).attr('font-size','9px').attr('fill','#e2e8f0')
                .attr('text-anchor','middle').attr('dy',32).style('pointer-events','none').style('user-select','none');
            container.addEventListener('click',()=>{ document.getElementById('graph-detail').innerHTML=''; });
            _sim = d3.forceSimulation(data.nodes)
                .force('link',d3.forceLink(data.edges).id(d=>d.id).distance(180).strength(0.3))
                .force('charge',d3.forceManyBody().strength(-400))
                .force('center',d3.forceCenter(W/2,H/2))
                .force('collide',d3.forceCollide().radius(30))
                .on('tick',()=>{
                    link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
                    node.attr('transform',d=>'translate('+d.x+','+d.y+')');
                });
        }
        function openHistoryModal(hist, keys) {
            let html = '';
            keys.forEach(v => {
                const h = hist[v];
                html += '<tr><td style="color:var(--text-muted);font-weight:600;width:35%">' + escapeHtml(v) + '</td>'
                      + '<td style="font-size:0.78rem;color:var(--text-muted)">code: ' + (h.search_code_calls||0)
                      + ' \xb7 notes: ' + (h.search_notes_calls||0)
                      + ' \xb7 saved: ' + (h.last_saved ? new Date(h.last_saved).toLocaleDateString() : '?') + '</td></tr>';
            });
            document.getElementById('history-modal-body').innerHTML = html || '<tr><td class="empty" colspan="2">No data</td></tr>';
            const m = document.getElementById('history-modal');
            m.style.display = 'flex';
            m.onclick = e => { if (e.target === m) closeHistoryModal(); };
        }
        function closeHistoryModal() {
            document.getElementById('history-modal').style.display = 'none';
        }
        document.addEventListener('keydown', e => { if (e.key === 'Escape') closeHistoryModal(); });
    </script>
    <div id="history-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;align-items:center;justify-content:center">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem;width:90%;max-width:540px;max-height:80vh;overflow-y:auto">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">
          <span style="font-weight:700;font-size:0.95rem">Past Versions</span>
          <button onclick="closeHistoryModal()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1.1rem;line-height:1">&#x2715;</button>
        </div>
        <table class="webhook-table" style="width:100%"><tbody id="history-modal-body"></tbody></table>
      </div>
    </div>
</body>
</html>"""

UI_HTML = _UI_TEMPLATE.replace("__LOGO__", LOGO_SVG)
