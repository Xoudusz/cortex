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
        /* Layered tokens (Atreia-style): bg < panel < panel2/3, line < line2, one accent + its rgb for tints.
           A theme is one html[data-theme=x] block overriding these. Old names stay as aliases. */
        :root {
            --bg: #0f1116; --bg2: #13161d;
            --panel: #181b24; --panel2: #1d2130; --panel3: #242a3b;
            --line: #262b3b; --line2: #353c53;
            --text: #e2e8f0; --muted: #8896a8; --dim: #5d6779;
            --accent: #a78bfa; --accent2: #c4b5fd; --acc-rgb: 167,139,250;
            --ok: #34d399; --err: #f87171; --err-rgb: 248,113,113;
            --mono: 'SF Mono', 'Fira Code', Consolas, monospace;
            --surface: var(--panel); --border: var(--line); --text-muted: var(--muted);
            --accent-hover: var(--accent2); --accent-dim: rgba(var(--acc-rgb),.12); --accent-glow: rgba(var(--acc-rgb),.2);
            --success: var(--ok); --error: var(--err);
        }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 1.25rem 1.5rem; font-size: 14px; }
        .container { max-width: 1120px; margin: 0 auto; }
        .ico { width: 15px; height: 15px; flex: none; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; vertical-align: -3px; }

        /* header: brand left, live stats + status right */
        .header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; padding-bottom: 0.9rem; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
        .logo-svg { width: 26px; height: 26px; flex-shrink: 0; }
        .header-text h1 { font-size: 1.1rem; font-weight: 700; letter-spacing: -0.01em; color: var(--accent2); line-height: 1.1; }
        .header-text span { font-size: 0.72rem; color: var(--dim); }
        .hstats { margin-left: auto; display: flex; align-items: center; gap: 1.1rem; font-size: 0.78rem; color: var(--muted); }
        .hstat b { color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; margin-right: 0.25rem; }
        .hdot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--dim); margin-right: 0.35rem; vertical-align: 1px; }
        .hdot.ok { background: var(--ok); } .hdot.error { background: var(--err); }
        .status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); display: none; }
        .status-dot.active { display: inline-block; animation: pulse-dot 1.2s ease-in-out infinite; }
        #status-text { display: flex; align-items: center; gap: 0.4rem; }
        @keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

        .tabs { display: flex; gap: 0.2rem; margin-bottom: 1.25rem; background: var(--panel); border: 1px solid var(--line); padding: 0.2rem; border-radius: 9px; width: fit-content; }
        .tab { display: flex; align-items: center; gap: 0.4rem; background: transparent; border: none; color: var(--muted); padding: 0.4rem 0.9rem; cursor: pointer; border-radius: 7px; font-size: 0.8125rem; font-weight: 500; }
        .tab:hover { color: var(--text); background: rgba(var(--acc-rgb),.06); }
        .tab.active { background: rgba(var(--acc-rgb),.14); color: var(--accent2); }
        .panel { display: none; } .panel.active { display: block; }

        /* inputs + buttons: flat, hover = accent tint, no lift/glow */
        .search-form { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }
        input[type="text"], input[type="password"], input:not([type]) { flex: 1; padding: 0.55rem 0.85rem; background: var(--bg2); border: 1px solid var(--line); border-radius: 8px; color: var(--text); font-size: 0.85rem; }
        input:focus, select:focus { outline: none; border-color: rgba(var(--acc-rgb),.6); box-shadow: 0 0 0 3px rgba(var(--acc-rgb),.12); }
        input::placeholder { color: var(--dim); }
        select { padding: 0.45rem 0.7rem; background: var(--bg2); border: 1px solid var(--line); border-radius: 8px; color: var(--text); font-size: 0.8125rem; cursor: pointer; }
        button { display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; padding: 0.5rem 1rem; background: var(--accent); border: 1px solid transparent; border-radius: 8px; color: #16121f; cursor: pointer; font-size: 0.83rem; font-weight: 600; transition: background .12s, color .12s, border-color .12s; }
        button:hover { background: var(--accent2); }
        button:disabled { opacity: 0.4; cursor: not-allowed; }
        button.secondary { background: var(--panel2); border-color: var(--line); color: var(--text); font-weight: 500; }
        button.secondary:hover { background: rgba(var(--acc-rgb),.12); border-color: rgba(var(--acc-rgb),.35); color: var(--accent2); }
        button.small { padding: 0.28rem 0.65rem; font-size: 0.75rem; }
        button.danger { background: rgba(var(--err-rgb),.1); border-color: rgba(var(--err-rgb),.3); color: var(--err); }
        button.danger:hover { background: rgba(var(--err-rgb),.2); }
        /* icon button: quiet until hovered */
        .ib { padding: 0; width: 28px; height: 28px; background: transparent; border: 1px solid transparent; color: var(--muted); border-radius: 7px; }
        .ib:hover { background: rgba(var(--acc-rgb),.14); color: var(--accent2); border-color: transparent; }
        .ib.del:hover { background: rgba(var(--err-rgb),.14); color: var(--err); }
        .ib:disabled:hover { background: transparent; color: var(--muted); }

        .toggles { display: flex; gap: 1.1rem; align-items: center; margin-bottom: 0.75rem; flex-wrap: wrap; }
        .toggle { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8125rem; color: var(--muted); cursor: pointer; }
        .toggle input { accent-color: var(--accent); }
        .repo-filter-row { display: flex; align-items: center; gap: 0.5rem; }
        .repo-filter-label { font-size: 0.75rem; color: var(--muted); white-space: nowrap; }
        .results { display: flex; flex-direction: column; gap: 0.6rem; }
        .result-card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 0.85rem 1rem; }
        .result-card:hover { border-color: var(--line2); }
        .result-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem; gap: 1rem; }
        .result-title { font-weight: 600; font-size: 0.8125rem; color: var(--accent2); word-break: break-all; line-height: 1.4; }
        .result-meta { font-size: 0.7rem; color: var(--dim); text-align: right; white-space: nowrap; flex-shrink: 0; }
        .result-content { font-size: 0.78rem; color: var(--muted); white-space: pre-wrap; max-height: 180px; overflow-y: auto; background: var(--bg2); padding: 0.6rem 0.75rem; border-radius: 6px; font-family: var(--mono); line-height: 1.5; }
        .result-tags { margin-top: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap; }
        .tag { background: rgba(var(--acc-rgb),.1); padding: 0.1rem 0.45rem; border-radius: 4px; font-size: 0.7rem; color: var(--accent2); }
        .section-title { font-size: 0.7rem; font-weight: 600; color: var(--dim); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 0.6rem; }

        /* admin: left nav + content (desktop), scrolling tab row (narrow) */
        .admin-layout { display: grid; grid-template-columns: 180px minmax(0,1fr); gap: 1.25rem; align-items: start; }
        .admin-tabs { display: flex; flex-direction: column; gap: 0.15rem; position: sticky; top: 1rem; }
        .admin-tab { justify-content: flex-start; background: transparent; border: none; color: var(--muted); padding: 0.45rem 0.7rem; font-size: 0.82rem; font-weight: 500; border-radius: 7px; white-space: nowrap; }
        .admin-tab:hover { color: var(--text); background: rgba(var(--acc-rgb),.06); }
        .admin-tab.active { color: var(--accent2); background: rgba(var(--acc-rgb),.14); }
        .admin-layout > div { min-width: 0; }
        .admin-section { display: none; } .admin-section.active { display: block; }
        #reindex-log-wrap, #webhook-log-wrap, #admin-graph .card { overflow-x: auto; }
        .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 0.9rem; }
        .card-h { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
        .sv-hero { font-size: 1.9rem; font-weight: 700; color: var(--text); line-height: 1.1; }
        .sv-hero small { font-size: 0.8rem; font-weight: 400; color: var(--muted); margin-left: 0.35rem; }
        .sv-formula { font-size: 0.72rem; color: var(--dim); margin: 0.3rem 0 0.7rem; }
        .sv-bar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--panel3); }
        .sv-obs { background: var(--ok); display: block; height: 100%; }
        .sv-mod { background: var(--accent); display: block; height: 100%; }
        .sv-legend { display: flex; flex-wrap: wrap; gap: 0.4rem 1.1rem; font-size: 0.75rem; color: var(--muted); margin: 0.4rem 0 0.7rem; }
        .sv-legend i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 0.3rem; }
        .sv-sec { font-size: 0.75rem; color: var(--muted); margin: 0.9rem 0 0.3rem; }
        .sv-mini { display: flex; height: 6px; min-width: 60px; border-radius: 3px; overflow: hidden; background: var(--panel3); }
        .card-h h3 { font-size: 0.88rem; font-weight: 600; }
        .card-h .sub { font-size: 0.75rem; color: var(--dim); }
        .card-h .push { margin-left: auto; display: flex; gap: 0.4rem; align-items: center; }
        .hint { font-size: 0.76rem; color: var(--muted); line-height: 1.55; }
        .hint code { font-family: var(--mono); font-size: 0.72rem; background: var(--bg2); padding: 0 0.25rem; border-radius: 3px; }
        .reindex-buttons { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
        /* tools dropdown */
        .dd { position: relative; }
        .dd > summary { list-style: none; }
        .dd > summary::-webkit-details-marker { display: none; }
        .ddp { position: absolute; right: 0; top: calc(100% + 4px); z-index: 20; min-width: 220px; background: var(--panel2); border: 1px solid var(--line2); border-radius: 9px; padding: 0.3rem; box-shadow: 0 8px 24px rgba(0,0,0,.45); }
        .ddi { display: flex; width: 100%; align-items: center; gap: 0.5rem; padding: 0.45rem 0.6rem; background: transparent; border: none; border-radius: 6px; color: var(--text); font-size: 0.8rem; font-weight: 400; cursor: pointer; justify-content: flex-start; }
        .ddi:hover { background: rgba(var(--acc-rgb),.14); }
        .ddi input { accent-color: var(--accent); }
        .ddsep { height: 1px; background: var(--line); margin: 0.25rem 0.2rem; }
        .status-log { background: var(--bg2); border: 1px solid var(--line); border-radius: 8px; padding: 0.75rem 0.9rem; font-family: var(--mono); font-size: 0.72rem; max-height: 280px; overflow-y: auto; white-space: pre-wrap; color: var(--muted); line-height: 1.5; margin-top: 0.75rem; }
        .status-running { border-color: rgba(var(--acc-rgb),.5); }
        .webhook-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
        .webhook-table th { text-align: left; padding: 0.45rem 0.6rem; color: var(--dim); font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid var(--line); }
        .webhook-table td { padding: 0.45rem 0.6rem; border-bottom: 1px solid rgba(38,43,59,.6); font-family: var(--mono); font-size: 0.76rem; }
        .webhook-table tr:last-child td { border-bottom: none; }
        .wh-triggered { color: var(--ok); } .wh-done { color: var(--muted); } .wh-failed { color: var(--err); } .wh-skipped { color: var(--dim); }

        /* repos: one quiet row each, actions are icons */
        .repo-item { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 0.5rem 0.5rem 0.5rem 0.85rem; margin-bottom: 0.35rem; }
        .repo-item:hover { border-color: var(--line2); }
        .repo-item.untracked { background: transparent; border-style: dashed; }
        .repo-item.untracked .repo-name { color: var(--muted); }
        .repo-info { display: flex; align-items: center; gap: 0.6rem; min-width: 0; flex: 1; flex-wrap: wrap; }
        .repo-error { flex-basis: 100%; min-width: 0; font-size: 0.72rem; line-height: 1.4; color: #fecdd3; white-space: normal; overflow-wrap: anywhere; }
        .repo-error .repo-badge { background: rgba(var(--err-rgb),.15); color: #fecdd3; margin-right: 0.4rem; }
        .repo-name { font-size: 0.8125rem; font-family: var(--mono); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
        .repo-meta { display: flex; align-items: center; gap: 0.4rem; flex-shrink: 0; }
        .repo-badge { font-size: 0.66rem; background: rgba(var(--acc-rgb),.12); color: var(--accent2); padding: 0.08rem 0.4rem; border-radius: 4px; }
        .repo-age { font-size: 0.7rem; color: var(--dim); }
        .repo-actions { display: flex; gap: 0.15rem; flex-shrink: 0; }
        .message { padding: 0.55rem 0.85rem; border-radius: 8px; margin-bottom: 0.75rem; font-size: 0.8125rem; }
        .message.error { background: rgba(var(--err-rgb),.1); border: 1px solid rgba(var(--err-rgb),.2); color: var(--err); }
        .message.info { background: rgba(var(--acc-rgb),.1); border: 1px solid rgba(var(--acc-rgb),.2); color: var(--accent2); }
        .empty { color: var(--dim); font-style: italic; padding: 0.5rem 0; }
        .loading { opacity: 0.5; }
        a { color: var(--accent2); text-decoration: none; }
        a:hover { text-decoration: underline; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--line2); border-radius: 3px; }

        /* toasts + modal */
        #toasts { position: fixed; right: 1rem; bottom: 1rem; z-index: 2000; display: flex; flex-direction: column; gap: 0.4rem; align-items: flex-end; pointer-events: none; }
        .toast { pointer-events: auto; max-width: min(420px, calc(100vw - 2rem)); padding: 0.55rem 0.85rem; border-radius: 8px; font-size: 0.8rem; background: var(--panel3); border: 1px solid var(--line2); color: var(--text); box-shadow: 0 6px 20px rgba(0,0,0,.4); transition: opacity .3s, transform .3s; }
        .toast.info { border-color: rgba(var(--acc-rgb),.45); }
        .toast.error { border-color: rgba(var(--err-rgb),.55); color: #fecdd3; }
        .toast.out { opacity: 0; transform: translateY(6px); }
        .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1500; align-items: center; justify-content: center; padding: 1rem; }
        .modal-box { background: var(--panel2); border: 1px solid var(--line2); border-radius: 12px; padding: 1.1rem 1.2rem; width: 100%; max-width: 420px; }
        .modal-box .cm-msg { font-size: 0.88rem; line-height: 1.5; margin-bottom: 1rem; overflow-wrap: anywhere; }
        .modal-box .cm-row { display: flex; justify-content: flex-end; gap: 0.5rem; }
        /* repos sections */
        .avail > summary { cursor: pointer; list-style: none; margin-top: 1rem; user-select: none; }
        .avail > summary::-webkit-details-marker { display: none; }
        .avail > summary::before { content: '▸'; display: inline-block; margin-right: 0.4rem; transition: transform .15s; }
        .avail[open] > summary::before { transform: rotate(90deg); }
        /* settings: connect card */
        .chip { display: inline-flex; align-items: center; gap: 0.2rem; background: var(--bg2); border: 1px solid var(--line); border-radius: 999px; padding: 0.1rem 0.25rem 0.1rem 0.6rem; font-size: 0.75rem; margin: 0 0.3rem 0.3rem 0; }
        .chip .ib { width: 20px; height: 20px; }
        .picker { position: relative; flex: 1; min-width: 0; }
        .picker > input { width: 100%; }
        .picker-status { font-size: 0.75rem; color: var(--muted); margin-top: 0.3rem; }
        .picker-status:empty { display: none; }
        .picker-status.bad { color: var(--err); }
        .picker-list { position: absolute; top: 100%; left: 0; right: 0; z-index: 50; margin-top: 2px; max-height: 17rem; overflow-y: auto; background: var(--bg2); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.35); }
        .picker-item { padding: 0.45rem 0.75rem; font-size: 0.8rem; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .picker-item:hover, .picker-item.active { background: rgba(var(--acc-rgb),.14); color: var(--accent2); }
        .urow { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; border-top: 1px solid var(--line); padding: 0.55rem 0; }
        .urow b { min-width: 90px; }
        .cmd { display: flex; align-items: center; gap: 0.4rem; background: var(--bg2); border: 1px solid var(--line); border-radius: 8px; padding: 0.4rem 0.4rem 0.4rem 0.75rem; font-family: var(--mono); font-size: 0.76rem; margin: 0.5rem 0; }
        .cmd code { flex: 1; overflow-x: auto; white-space: nowrap; scrollbar-width: none; }
        /* logs */
        #log-output { white-space: normal; word-break: normal; }
        #log-output > div { white-space: pre; }
        #log-output .lg-err { color: #fca5a5; } #log-output .lg-warn { color: #fcd34d; }
        .result-meta .ib { width: 24px; height: 24px; vertical-align: middle; }
        .result-meta { display: flex; align-items: center; gap: 0.35rem; }
        @media (max-width: 720px) {
            .card-h { flex-wrap: wrap; } .card-h .sub { order: 3; flex-basis: 100%; }
            .result-header { flex-direction: column; gap: 0.35rem; } .result-meta { text-align: left; }
            body { padding: 1rem 0.85rem; }
            .hstats { margin-left: 0; width: 100%; gap: 0.9rem; flex-wrap: wrap; }
            .tabs { width: 100%; } .tab { flex: 1; justify-content: center; padding: 0.45rem 0.4rem; }
            .admin-layout { grid-template-columns: minmax(0,1fr); gap: 0.75rem; }
            /* wrap instead of a hidden horizontal scroll: every section (Users, Settings) stays visible */
            .admin-tabs { flex-direction: row; flex-wrap: wrap; gap: 0.25rem; position: static; border-bottom: 1px solid var(--line); padding-bottom: 0.35rem; }
            .admin-tab { flex: 0 0 auto; }
            /* iOS Safari zooms into any focused field under 16px */
            input, select, textarea { font-size: 16px !important; }
        }
    </style>
</head>
<body>
    <svg width="0" height="0" style="position:absolute" aria-hidden="true">
        <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></symbol>
        <symbol id="i-repos" viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></symbol>
        <symbol id="i-admin" viewBox="0 0 24 24"><path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/></symbol>
        <symbol id="i-graph" viewBox="0 0 24 24"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/></symbol>
        <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></symbol>
        <symbol id="i-trash" viewBox="0 0 24 24"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></symbol>
        <symbol id="i-plus" viewBox="0 0 24 24"><path d="M5 12h14M12 5v14"/></symbol>
        <symbol id="i-more" viewBox="0 0 24 24"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></symbol>
        <symbol id="i-zap" viewBox="0 0 24 24"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></symbol>
        <symbol id="i-copy" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></symbol>
        <symbol id="i-ext" viewBox="0 0 24 24"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></symbol>
        <symbol id="i-logout" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></symbol>
        <symbol id="i-eraser" viewBox="0 0 24 24"><path d="m7 21-4.3-4.3a1 1 0 0 1 0-1.4l10-10a1 1 0 0 1 1.4 0l5.6 5.6a1 1 0 0 1 0 1.4L11 21M22 21H7M5 11l9 9"/></symbol>
    </svg>
    <div class="container">
        <div class="header">
            __LOGO__
            <div class="header-text">
                <h1>Cortex</h1>
                <span>RAG Dashboard</span>
            </div>
            <div class="hstats">
                <span class="hstat"><b id="stat-notes">-</b>notes</span>
                <span class="hstat"><b id="stat-code">-</b>code chunks</span>
                <span class="hstat"><span class="hdot" id="stat-ollama"></span>Ollama</span>
                <span class="hstat" id="status-text"><span id="status-dot" class="status-dot"></span><span id="status-label">idle</span></span>
                <select id="ws-switch" title="Workspace" style="display:none;max-width:12rem"></select>
                <button class="ib" id="sign-out" title="Sign out"><svg class="ico"><use href="#i-logout"/></svg></button>
            </div>
        </div>

        <div id="member-view" style="display:none">
            <div class="card">
                <div class="card-h"><h3>Hi <span id="mv-user"></span></h3><span class="sub">you use Cortex through Claude Code</span></div>
                <div class="hint">Your workspaces: <b id="mv-ws"></b></div>
                <div class="cmd"><code id="mv-cmd"></code><button class="ib" id="mv-copy" title="Copy"><svg class="ico"><use href="#i-copy"/></svg></button></div>
                <div class="hint">Run this once where Claude Code runs. The first tool call opens a browser login: use your username and password.
                Then ask Claude to <code>list_workspaces</code>, <code>switch_workspace</code>, and search with <code>search_code</code> / <code>search_notes</code>.</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="search"><svg class="ico"><use href="#i-search"/></svg>Search</button>
            <button class="tab" data-tab="repos"><svg class="ico"><use href="#i-repos"/></svg>Repos</button>
            <button class="tab" data-tab="admin"><svg class="ico"><use href="#i-admin"/></svg>Admin</button>
            <button class="tab" data-tab="graph"><svg class="ico"><use href="#i-graph"/></svg>Graph</button>
        </div>

        <div id="search-panel" class="panel active">
            <form class="search-form" id="search-form">
                <input type="text" id="query" placeholder="Search notes and code...">
                <button type="submit"><svg class="ico"><use href="#i-search"/></svg>Search</button>
            </form>
            <div class="toggles">
                <label class="toggle"><input type="checkbox" id="search-notes" checked><span>Notes</span></label>
                <label class="toggle"><input type="checkbox" id="search-code" checked><span>Code</span></label>
                <div class="repo-filter-row" id="repo-filter-row" style="display:none">
                    <span class="repo-filter-label">in</span>
                    <select id="repo-filter"><option value="">All repos</option></select>
                </div>
            </div>
            <div id="search-results" class="results"><div class="empty">Search your notes and code. Claude Code runs the same search through <code>search_notes</code> / <code>search_code</code>.</div></div>
        </div>

        <div id="repos-panel" class="panel">
            <div class="card-h" style="margin-bottom:0.6rem"><h3 id="repos-title">Repos</h3></div>
            <form id="repo-add-form" class="search-form">
                <input id="repo-add-input" placeholder="Filter, or add owner/name" autocomplete="off">
                <button type="submit"><svg class="ico"><use href="#i-plus"/></svg>Add repo</button>
            </form>
            <div id="repo-gh-warning" class="hint" style="display:none;margin-bottom:0.5rem"></div>
            <div id="repo-message"></div>
            <div id="repo-list"></div>
        </div>

        <div id="admin-panel" class="panel">
          <div class="admin-layout">
            <nav class="admin-tabs">
                <button class="admin-tab active" data-admin-tab="reindex">Reindex</button>
                <button class="admin-tab" data-admin-tab="graph">Graph efficiency</button>
                <button class="admin-tab" data-admin-tab="webhooks">Webhooks</button>
                <button class="admin-tab" data-admin-tab="logs">Logs</button>
                <button class="admin-tab" data-admin-tab="users">Users</button>
                <button class="admin-tab" data-admin-tab="settings">Settings</button>
            </nav>
            <div>
            <div id="admin-reindex" class="admin-section active">
                <div class="card">
                    <div class="card-h"><h3>Reindex</h3><span class="sub">notes from the vault, code from tracked repos</span></div>
                    <div class="reindex-buttons">
                        <button id="reindex-all"><svg class="ico"><use href="#i-refresh"/></svg>Reindex all</button>
                        <button id="reindex-notes" class="secondary">Notes</button>
                        <button id="reindex-code" class="secondary">Code</button>
                        <details class="dd" id="reindex-tools" style="margin-left:auto">
                            <summary class="ib" title="More"><svg class="ico"><use href="#i-more"/></svg></summary>
                            <div class="ddp">
                                <label class="ddi"><input type="checkbox" id="force-reindex"><svg class="ico"><use href="#i-zap"/></svg>Force re-embed (clear cache first)</label>
                                <div class="ddsep"></div>
                                <button type="button" class="ddi" id="clear-cache-btn"><svg class="ico"><use href="#i-eraser"/></svg>Clear cache only</button>
                            </div>
                        </details>
                    </div>
                    <div id="queue-list" class="hint" style="display:none;margin-top:0.6rem"></div>
                    <div id="reindex-status" class="status-log">No reindex running.</div>
                </div>
                <div class="card"><div class="card-h"><h3>Job history</h3></div><div id="reindex-log-wrap"><div class="empty">No jobs run yet.</div></div></div>
            </div>
            <div id="admin-graph" class="admin-section">
                <div class="card">
                    <div class="card-h"><h3>Graph efficiency</h3><span class="sub">search + cache counters since start</span><span class="push"><button id="history-btn" class="secondary small" style="display:none">Past versions</button></span></div>
                    <table class="webhook-table"><tbody id="graph-stats-body"><tr><td colspan="2" class="empty">Loading...</td></tr></tbody></table>
                </div>
                <div class="card" id="savings-card">
                    <div class="card-h"><h3>Token savings</h3><span class="sub">estimated tokens agents did not read &middot; ~bytes/4</span></div>
                    <div id="savings-body"><div class="empty">Loading...</div></div>
                </div>
            </div>
            <div id="admin-webhooks" class="admin-section">
                <div class="card"><div class="card-h"><h3>Webhooks</h3><span class="sub">GitHub pushes that triggered a reindex</span></div><div id="webhook-log-wrap"><div class="empty">No webhooks received yet.</div></div></div>
            </div>
            <div id="admin-users" class="admin-section">
                <div class="card">
                    <div class="card-h"><h3>Current workspace</h3><span class="sub" id="ws-current-sub"></span></div>
                    <div id="ws-current"></div>
                </div>
                <div class="card">
                    <div class="card-h"><h3>New shared workspace</h3><span class="sub">own code + notes index; your vault stays private in <code>default</code></span></div>
                    <form id="ws-create-form" style="display:flex;gap:0.5rem;flex-wrap:wrap">
                        <input id="ws-name" placeholder="name, e.g. proj" autocomplete="off" style="flex:1;min-width:140px">
                        <input id="ws-wiki" placeholder="wiki repo owner/name (optional)" autocomplete="off" style="flex:2;min-width:200px">
                        <button type="submit"><svg class="ico"><use href="#i-plus"/></svg>Create</button>
                    </form>
                    <div class="hint" style="margin-top:0.5rem">The wiki repo is a GitHub repo of markdown files indexed as the workspace's notes; a push reindexes it (add the cortex webhook to it).</div>
                </div>
                <div class="card">
                    <div class="card-h"><h3>Users</h3><span class="sub">invite links are single use and valid 7 days</span></div>
                    <form id="invite-form" style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center">
                        <input id="invite-name" placeholder="username" autocomplete="off" style="flex:1;min-width:140px">
                        <button type="submit"><svg class="ico"><use href="#i-plus"/></svg>Invite</button>
                        <span id="invite-hint" class="hint"></span>
                    </form>
                    <div id="invite-result"></div>
                    <div id="user-list" style="margin-top:0.75rem"></div>
                </div>
            </div>
            <div id="admin-settings" class="admin-section">
                <div class="card">
                    <div class="card-h"><h3>Connect Claude Code</h3><span class="sub">run once on the machine that runs Claude Code</span></div>
                    <div class="cmd"><code id="connect-cmd"></code><button class="ib" id="connect-copy" title="Copy"><svg class="ico"><use href="#i-copy"/></svg></button></div>
                    <div class="hint">The first tool call opens this login in a browser. After that, <code>search_notes</code>, <code>search_code</code> and <code>reindex</code> are available in every session.</div>
                </div>
                <div class="card">
                    <div class="card-h"><h3>GitHub token</h3><span class="sub">lists repos, clones private ones</span></div>
                    <div id="token-status" style="font-size:0.82rem;margin-bottom:0.75rem;color:var(--muted)">Loading...</div>
                    <form id="token-form" style="display:flex;gap:0.5rem;flex-wrap:wrap">
                        <input id="token-input" type="password" placeholder="ghp_... or github_pat_..." autocomplete="off" style="flex:1;min-width:220px">
                        <button type="submit">Save</button>
                        <button type="button" id="token-clear" class="secondary">Clear (use env var)</button>
                    </form>
                    <div id="token-message" style="margin-top:0.6rem"></div>
                    <div class="hint" style="margin-top:0.6rem">
                        Checked against GitHub before saving; stored in <code>data/settings.json</code> (mode 600), overrides the <code>GITHUB_TOKEN</code> env var.<br>
                        Private repos owned by <b>someone else</b> (you are a collaborator) need a <b>classic</b> PAT with <code>repo</code> scope; fine-grained PATs can't see them.
                    </div>
                </div>
            </div>
            <div id="admin-logs" class="admin-section">
                <div class="card">
                    <div class="card-h"><h3>Server log</h3><span class="sub">last 200 lines</span><span class="push"><select id="log-level" title="Level"><option value="all">All</option><option value="warn">Warnings + errors</option><option value="err">Errors</option></select><label class="toggle"><input type="checkbox" id="log-tail-toggle">follow</label><button onclick="loadLogs()" class="ib" title="Refresh"><svg class="ico"><use href="#i-refresh"/></svg></button></span></div>
                    <div id="log-output" class="status-log" style="max-height:420px;margin-top:0">No logs loaded.</div>
                </div>
            </div>
            </div>
          </div>
        </div>

        <div id="graph-panel" class="panel">
            <div style="display:flex;gap:0.5rem;margin-bottom:0.75rem;align-items:center">
                <select id="graph-repo-select" style="flex:1"><option value="notes">Notes (wikilinks)</option><option value="global">★ Global (cross-repo)</option></select>
                <button id="graph-load-btn" class="secondary" style="flex-shrink:0">Load graph</button>
            </div>
            <div id="graph-info" style="font-size:0.75rem;color:var(--text-muted);margin-bottom:0.5rem;min-height:1.2em"></div>
            <div id="graph-container" style="width:100%;height:min(640px,70vh);background:var(--bg2);border:1px solid var(--border);border-radius:10px;overflow:hidden;position:relative">
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

        // Auth (issue #8): initAuth() is the single entry point. Every api() call awaits
        // authReady, so no request runs (and no 401 can restart OAuth) while a ?code=
        // exchange is still in flight. startOAuthFlow() runs at most once per page and
        // stores the verifier together with the challenge it navigates with.
        let oauthStarted = false;
        function startOAuthFlow() {
            if (oauthStarted) return;
            oauthStarted = true;
            const verifier = generateVerifier();
            // One verifier per login attempt, keyed by a random state, so two tabs never clobber each other.
            const state = generateVerifier();
            crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)).then(hash => {
                const challenge = btoa(String.fromCharCode(...new Uint8Array(hash)))
                    .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
                localStorage.setItem('cortex_pkce_' + state, JSON.stringify({ v: verifier, t: Date.now() }));
                const redirectUri = window.location.origin + '/';
                const params = new URLSearchParams({
                    response_type: 'code',
                    client_id: 'cortex-web-ui',
                    redirect_uri: redirectUri,
                    code_challenge: challenge,
                    code_challenge_method: 'S256',
                    state: state,
                });
                window.location.href = '/oauth/authorize?' + params.toString();
            });
        }

        function showAuthError(message) {
            const box = document.createElement('div');
            box.id = 'auth-error';
            box.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:1000;padding:12px 16px;border-radius:8px;background:#3b1d2a;color:#fecdd3;border:1px solid #be123c;font:14px system-ui;max-width:90vw';
            box.textContent = 'Sign-in failed: ' + message + ' ';
            const retry = document.createElement('button');
            retry.textContent = 'Sign in again';
            retry.style.cssText = 'margin-left:8px;cursor:pointer';
            retry.onclick = () => { oauthStarted = false; startOAuthFlow(); };
            box.appendChild(retry);
            document.body.appendChild(box);
        }

        function saveTokens(data) {
            localStorage.setItem('cortex_token', data.access_token);
            if (data.refresh_token) localStorage.setItem('cortex_refresh', data.refresh_token);
        }

        // Single-flight refresh: concurrent 401s share one POST /token.
        let refreshing = null;
        function refreshAccessToken() {
            const rt = localStorage.getItem('cortex_refresh');
            if (!rt) return Promise.resolve(false);
            if (!refreshing) {
                refreshing = (async () => {
                    try {
                        const res = await fetch('/token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                            body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: rt, client_id: 'cortex-web-ui' }),
                        });
                        if (!res.ok) { localStorage.removeItem('cortex_refresh'); return false; }
                        saveTokens(await res.json());
                        return true;
                    } catch (_) {
                        return false;
                    } finally {
                        setTimeout(() => { refreshing = null; }, 0);
                    }
                })();
            }
            return refreshing;
        }

        const authReady = (async function initAuth() {
            const params = new URLSearchParams(window.location.search);
            const code = params.get('code');
            if (code) {
                history.replaceState({}, '', '/');
                const stateKey = 'cortex_pkce_' + (params.get('state') || '');
                let verifier = '';
                try { verifier = (JSON.parse(localStorage.getItem(stateKey) || 'null') || {}).v || ''; } catch (_) {}
                localStorage.removeItem(stateKey);
                localStorage.removeItem('cortex_pkce_verifier');
                const cutoff = Date.now() - 10 * 60 * 1000;
                Object.keys(localStorage).forEach(k => {
                    if (k.indexOf('cortex_pkce_') !== 0) return;
                    try { const s = JSON.parse(localStorage.getItem(k) || 'null'); if (!s || !s.t || s.t < cutoff) localStorage.removeItem(k); }
                    catch (_) { localStorage.removeItem(k); }
                });
                if (!verifier) {
                    // Another tab already finished this login: keep its token instead of erroring.
                    if (getToken()) return true;
                    showAuthError('no PKCE verifier in this browser (opened in another tab?).'); return false;
                }
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
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        showAuthError(err.error_description || err.error || ('HTTP ' + res.status));
                        return false;
                    }
                    saveTokens(await res.json());
                    return true;
                } catch (e) {
                    showAuthError(e.message || 'network error');
                    return false;
                }
            }
            if (getToken()) return true;
            if (await refreshAccessToken()) return true;
            startOAuthFlow();
            return false;
        })();

        // Workspace picked in the header switcher; the server scopes admin /api/* calls to it.
        function currentWs() { return localStorage.getItem('cortex_ws') || 'default'; }

        async function api(path, options = {}, retried = false) {
            await authReady;
            const token = getToken();
            const headers = { 'Content-Type': 'application/json', 'X-Cortex-Workspace': currentWs(), ...options.headers };
            if (token) headers['Authorization'] = 'Bearer ' + token;
            const res = await fetch(path, { ...options, headers });
            if (res.status === 401) {
                // Only drop the token this request used: a newer one may have been stored meanwhile.
                if (token && getToken() === token) localStorage.removeItem('cortex_token');
                if (!retried) {
                    const current = getToken();
                    if (current && current !== token) return api(path, options, true);
                    if (await refreshAccessToken()) return api(path, options, true);
                }
                startOAuthFlow();
                return;
            }
            if (!res.ok) { const err = await res.json().catch(() => ({ error: res.statusText })); throw new Error(err.error || res.statusText); }
            return res.json();
        }

        // Members (non-admin users) only get the connect card; the dashboard API is admin-only.
        const roleReady = (async function initRole() {
            let me;
            try { me = await api('/api/me'); } catch (_) { return false; }
            if (!me) return false;
            if (me.admin) return true;
            document.querySelectorAll('.tabs, .panel, .hstats .hstat').forEach(el => { el.style.display = 'none'; });
            document.getElementById('member-view').style.display = 'block';
            document.getElementById('mv-user').textContent = me.user;
            document.getElementById('mv-ws').textContent = (me.workspaces || []).join(', ') || 'none yet - ask the admin';
            const cmd = 'claude mcp add cortex --transport sse ' + window.location.origin + '/sse';
            document.getElementById('mv-cmd').textContent = cmd;
            document.getElementById('mv-copy').addEventListener('click', () => copyText(cmd));
            document.getElementById('ws-switch').style.display = 'none';
            return false;
        })();

        // Header workspace switcher (admins). Options: default (private) + shared workspaces.
        function switchWs(ws) { localStorage.setItem('cortex_ws', ws); location.reload(); }
        async function loadWsSwitcher() {
            const sel = document.getElementById('ws-switch');
            try {
                const data = await api('/api/workspaces');
                if (!data) return;
                const names = (data.workspaces || []).map(w => w.name);
                const cur = currentWs();
                // Stored workspace was deleted or never existed here: fall back to default once.
                if (cur !== 'default' && !names.includes(cur)) { localStorage.setItem('cortex_ws', 'default'); location.reload(); return; }
                sel.innerHTML = '<option value="default">default (private)</option>' +
                    names.map(n => '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>').join('');
                sel.value = cur;
                sel.style.display = '';
                sel.onchange = () => switchWs(sel.value);
                document.getElementById('repos-title').textContent = 'Repos · ' + cur;
            } catch (err) { toast(err.message, 'error'); }
        }
        roleReady.then(isAdmin => { if (isAdmin) loadWsSwitcher(); });

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
                if (tab.dataset.adminTab === 'settings') loadTokenStatus();
                if (tab.dataset.adminTab === 'users') loadUsersPanel();
            });
        });

        const statusDot = document.getElementById('status-dot');
        function setStatusLabel(data) {
            const q = (data.queue || []).length;
            document.getElementById('status-label').textContent = data.running ? ('indexing ' + jobLabel(data.current_job) + (q ? ' +' + q + ' queued' : '')) : (q ? q + ' queued' : 'idle');
        }
        async function pollStatusDot() { try { const data = await api('/api/status'); statusDot.classList.toggle('active', !!data.running); setStatusLabel(data); if ((data.running || (data.queue && data.queue.length)) && !statusPoll) pollStatus(); } catch (_) {} }
        roleReady.then(isAdmin => { if (isAdmin) { pollStatusDot(); setInterval(pollStatusDot, 5000); } });

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
        roleReady.then(isAdmin => { if (isAdmin) { loadRepoFilter(); loadStats(); } });
        // Focus search only with a mouse: on phones autofocus pops the keyboard on every visit.
        if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) document.getElementById('query').focus();

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
                    return '<div class="result-card"><div class="result-header"><div class="result-title">' + escapeHtml(r.file) + ' > ' + escapeHtml(r.heading) + '</div><div class="result-meta">score ' + r.score.toFixed(3) + copyBtn(r.file) + '</div></div><div class="result-content">' + escapeHtml(r.text) + '</div>' + (tags ? '<div class="result-tags">' + tags + '</div>' : '') + '</div>';
                } else {
                    const link = r.github_url ? '<a class="ib" href="' + escapeHtml(r.github_url) + '" target="_blank" rel="noopener" title="Open on GitHub"><svg class="ico"><use href="#i-ext"/></svg></a>' : '';
                    return '<div class="result-card"><div class="result-header"><div class="result-title">' + escapeHtml(r.repo) + ' / ' + escapeHtml(r.file) + ' :' + r.start_line + '-' + r.end_line + '</div><div class="result-meta">' + escapeHtml(r.language || '') + ' · ' + r.score.toFixed(3) + copyBtn(r.repo + '/' + r.file + ':' + r.start_line) + link + '</div></div><div class="result-content">' + escapeHtml(r.text) + '</div></div>';
                }
            }).join('');
        }

        async function loadStats() {
            try {
                const data = await api('/api/stats');
                document.getElementById('stat-notes').textContent = data.notes?.points_count?.toLocaleString() ?? '-';
                document.getElementById('stat-code').textContent = data.code?.points_count?.toLocaleString() ?? '-';
                const ollama = document.getElementById('stat-ollama');
                ollama.className = 'hdot ' + (data.ollama?.status === 'ok' ? 'ok' : 'error');
                ollama.parentElement.title = 'Ollama ' + (data.ollama?.status || 'unknown');
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
                        btn.textContent = 'Past versions (' + histKeys.length + ')';
                        btn.onclick = () => openHistoryModal(hist, histKeys);
                    } else {
                        btn.style.display = 'none';
                    }
                    renderSavings(g);
                }
            } catch (err) { console.error('Failed to load stats:', err); }
        }

        function fmtTok(n) {
            n = Math.round(n || 0);
            if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
            return String(n);
        }

        function renderSavings(g) {
            const body = document.getElementById('savings-body');
            if (!body) return;
            const obs = (g.tokens_observed_code || 0) + (g.tokens_observed_notes || 0);
            const mod = g.tokens_modeled_code || 0;
            const total = obs + mod;
            const hm = g.savings_hits_measured || 0;
            const hu = g.savings_hits_unmeasured || 0;
            if (!total && !hm && !hu) { body.innerHTML = '<div class="empty">No savings recorded yet.</div>'; return; }
            const pct = total ? (obs / total * 100) : 0;
            let h = '<div class="sv-hero">' + fmtTok(total) + '<small>tokens saved</small></div>';
            h += '<div class="sv-formula">observed = full file &minus; returned chunk (once per file/session) &middot; modeled = 50% &times; unreturned candidates</div>';
            h += '<div class="sv-bar"><span class="sv-obs" style="width:' + pct.toFixed(1) + '%"></span><span class="sv-mod" style="width:' + (total ? 100 - pct : 0).toFixed(1) + '%"></span></div>';
            h += '<div class="sv-legend"><span><i style="background:var(--ok)"></i>observed ' + fmtTok(obs) + '</span><span><i style="background:var(--accent)"></i>modeled ' + fmtTok(mod) + '</span></div>';
            h += '<div class="sv-formula" style="margin:0">hits measured ' + hm + ' &middot; unmeasured ' + hu + (hu > 0 ? ' <span class="repo-badge">reindex to measure</span>' : '') + '</div>';
            const tbl = (title, label, map) => {
                const rows = Object.entries(map || {}).map(([k, v]) => [k, (v && v.observed) || 0, (v && v.modeled) || 0, (v && v.hits) || 0])
                    .sort((a, b) => (b[1] + b[2]) - (a[1] + a[2]));
                if (!rows.length) return '';
                return '<div class="sv-sec">' + title + '</div><table class="webhook-table"><thead><tr><th>' + label + '</th><th>Observed</th><th>Modeled</th><th>Hits</th></tr></thead><tbody>'
                    + rows.map(r => '<tr><td>' + escapeHtml(r[0]) + '</td><td>' + fmtTok(r[1]) + '</td><td>' + fmtTok(r[2]) + '</td><td>' + r[3] + '</td></tr>').join('') + '</tbody></table>';
            };
            h += tbl('By repo', 'Repo', g.savings_by_repo);
            h += tbl('By user', 'User', g.savings_by_user);
            const hist = g.history || {};
            const tot = d => ((d && d.tokens_observed_code) || 0) + ((d && d.tokens_observed_notes) || 0) + ((d && d.tokens_modeled_code) || 0);
            const vers = Object.keys(hist).map(v => [v, hist[v]]);
            if (g.version) vers.push([String(g.version), g]);
            const p = v => v.split('.').map(x => parseInt(x, 10) || 0);
            vers.sort((a, b) => { const [a1, a2, a3] = p(a[0]); const [b1, b2, b3] = p(b[0]); return b1 - a1 || b2 - a2 || b3 - a3; });
            if (vers.length > 1) {
                const mx = Math.max(1, ...vers.map(x => tot(x[1])));
                h += '<div class="sv-sec">By version</div><table class="webhook-table"><tbody>'
                    + vers.map(([v, d]) => { const t = tot(d); return '<tr><td>' + escapeHtml(v) + '</td><td>' + fmtTok(t) + '</td><td style="width:45%"><div class="sv-mini"><span class="sv-obs" style="width:' + (t / mx * 100).toFixed(1) + '%"></span></div></td></tr>'; }).join('')
                    + '</tbody></table>';
            }
            body.innerHTML = h;
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
                const lvl = document.getElementById('log-level').value;
                const isErr = l => l.includes(' ERROR ') || l.includes(' CRITICAL ');
                const isWarn = l => l.includes(' WARNING ');
                const lines = data.lines.filter(l => lvl === 'all' || isErr(l) || (lvl === 'warn' && isWarn(l)));
                pre.innerHTML = lines.length ? lines.map(l => '<div class="' + (isErr(l) ? 'lg-err' : isWarn(l) ? 'lg-warn' : '') + '">' + escapeHtml(l) + '</div>').join('') : '<div class="empty">' + (data.lines.length ? 'No matching lines.' : 'Log file empty.') + '</div>';
                pre.scrollTop = pre.scrollHeight;
            } catch (err) { pre.textContent = 'Failed to load logs.'; }
        }
        document.getElementById('log-level').addEventListener('change', loadLogs);
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
            if (btn) { btn.disabled = true; btn._origHtml = btn.innerHTML; btn.lastChild.textContent += force ? ' (force queued)' : ' (queued)'; }
            try {
                await api('/api/reindex', { method: 'POST', body: JSON.stringify({ notes, code, repo: repo || '', force }) });
                pollStatus();
            } catch (err) {
                document.getElementById('reindex-status').textContent = 'Error: ' + err.message;
                toast('Reindex failed: ' + err.message, 'error');
                if (btn) { btn.disabled = false; btn.innerHTML = btn._origHtml; }
            }
        }

        document.getElementById('clear-cache-btn').addEventListener('click', async function() {
            const btn = this;
            btn.disabled = true; document.getElementById('reindex-tools').open = false;
            try {
                const data = await api('/api/clear-cache', { method: 'POST', body: JSON.stringify({ all_workspaces: false }) });
                document.getElementById('reindex-status').textContent = `Cache cleared (${data.deleted} file(s) deleted). Run reindex to rebuild.`;
            } catch (err) {
                document.getElementById('reindex-status').textContent = 'Error: ' + err.message;
            } finally {
                btn.disabled = false;
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
            [all, notes, code].forEach(b => { b.disabled = false; if (b._origHtml) { b.innerHTML = b._origHtml; delete b._origHtml; } });
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
                    setStatusLabel(data);
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
            updateQueueDisplay(data.current_job, data.queue);
            syncButtonStates(data.current_job, data.queue);
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
                const warn = document.getElementById('repo-gh-warning');
                let ghRepos = [];
                if (ghRes.status === 'fulfilled' && ghRes.value) {
                    ghRepos = ghRes.value.repos || [];
                    warn.style.display = 'none';
                } else {
                    warn.textContent = 'GitHub repo list unavailable: ' + (ghRes.reason ? ghRes.reason.message : 'unknown error') + '. Set a token in Admin > Settings, or add repos by name above.';
                    warn.style.display = 'block';
                }
                // tracked repos stay visible even if the token can't list them (added by name)
                renderRepos([...new Set([...ghRepos, ...indexedList])], indexedList, indexedAt, meta.errors || {});
            } catch (err) { listDiv.innerHTML = '<div class="message error">' + escapeHtml(err.message) + '</div>'; }
        }

        let _repoState = null;
        function renderRepos(allRepos, indexedList, indexedAt, errors = {}) {
            _repoState = { allRepos, indexedList, indexedAt, errors };
            const listDiv = document.getElementById('repo-list');
            const q = document.getElementById('repo-add-input').value.trim().toLowerCase();
            const indexedSet = new Set(indexedList);
            const match = r => !q || r.toLowerCase().includes(q);
            const tracked = allRepos.filter(r => indexedSet.has(r) && match(r)).sort((a, b) => a.localeCompare(b));
            const avail = allRepos.filter(r => !indexedSet.has(r) && match(r)).sort((a, b) => a.localeCompare(b));
            const row = repo => {
                const isTracked = indexedSet.has(repo);
                const name = repo.split('/')[1];
                const hasIndexedAt = isTracked && !!indexedAt[name];
                const age = hasIndexedAt ? timeAgo(indexedAt[name]) : '';
                const err = isTracked ? errors[name] : '';
                const errHtml = err ? '<div class="repo-error" title="' + escapeHtml(err) + '"><span class="repo-badge">index failed</span>' + escapeHtml(err.slice(0, 300)) + '</div>' : '';
                const status = hasIndexedAt ? '<div class="repo-meta"><span class="repo-badge">indexed</span><span class="repo-age">' + escapeHtml(age) + '</span></div>' : (isTracked && !err ? '<div class="repo-meta"><span class="repo-age">not indexed yet</span></div>' : '');
                const ic = n => '<svg class="ico"><use href="#i-' + n + '"/></svg>';
                const actions = isTracked
                    ? '<button class="ib repo-reindex-btn" title="Reindex ' + escapeHtml(name) + '">' + ic('refresh') + '</button><button class="ib del repo-remove-btn" title="Stop tracking ' + escapeHtml(name) + '">' + ic('trash') + '</button>'
                    : '<button class="ib repo-add-btn" title="Track and index ' + escapeHtml(name) + '">' + ic('plus') + '</button>';
                return '<div class="repo-item' + (isTracked ? '' : ' untracked') + '" data-repo="' + escapeHtml(repo) + '"><div class="repo-info"><span class="repo-name">' + escapeHtml(repo) + '</span>' + status + errHtml + '</div><div class="repo-actions">' + actions + '</div></div>';
            };
            let html = '<div class="section-title">Tracked (' + tracked.length + ')</div>';
            html += tracked.length ? tracked.map(row).join('') : '<div class="empty">' + (q ? 'No tracked repo matches "' + escapeHtml(q) + '".' : 'Nothing tracked yet. Type owner/name above, or pick a repo from the list below.') + '</div>';
            if (avail.length) html += '<details class="avail"' + (q || !indexedList.length ? ' open' : '') + '><summary class="section-title">Available on GitHub (' + avail.length + ')</summary>' + avail.map(row).join('') + '</details>';
            listDiv.innerHTML = html;
            listDiv.querySelectorAll('.repo-reindex-btn').forEach(btn => { btn.addEventListener('click', async () => { const repo = btn.closest('.repo-item').dataset.repo; const name = repo.split('/')[1]; btn.disabled = true; try { await triggerReindex(false, true, name); showRepoMsg('Reindexing ' + name + '...', 'info'); } catch (err) { showRepoMsg(err.message, 'error'); } finally { btn.disabled = false; } }); });
            listDiv.querySelectorAll('.repo-remove-btn').forEach(btn => { btn.addEventListener('click', async () => { const repo = btn.closest('.repo-item').dataset.repo; if (!await confirmDialog('Stop tracking ' + repo + '?', 'Stop tracking')) return; try { const data = await api('/api/repos/' + encodeURIComponent(repo), { method: 'DELETE' }); renderRepos(allRepos, data.repos || [], indexedAt, errors); showRepoMsg('Removed ' + repo.split('/')[1] + ' from index', 'info'); loadRepoFilter(); } catch (err) { showRepoMsg(err.message, 'error'); } }); });
            listDiv.querySelectorAll('.repo-add-btn').forEach(btn => { btn.addEventListener('click', async () => { const repo = btn.closest('.repo-item').dataset.repo; btn.disabled = true; try { const data = await api('/api/repos', { method: 'POST', body: JSON.stringify({ repo }) }); renderRepos(allRepos, data.repos || [], indexedAt, errors); const name = repo.split('/')[1]; showRepoMsg('Added ' + name + ' — indexing...', 'info'); await triggerReindex(false, true, name); loadRepoFilter(); } catch (err) { showRepoMsg(err.message, 'error'); btn.disabled = false; } }); });
        }

        document.getElementById('repo-add-input').addEventListener('input', () => { if (_repoState) { const st = _repoState; renderRepos(st.allRepos, st.indexedList, st.indexedAt, st.errors); } });
        document.getElementById('repo-add-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = document.getElementById('repo-add-input');
            const repo = normalizeRepoInput(input.value);
            const parts = repo.split('/');
            if (parts.length !== 2 || !parts[0] || !parts[1]) { showRepoMsg('Use owner/name', 'error'); return; }
            try {
                await api('/api/repos', { method: 'POST', body: JSON.stringify({ repo }) });
                input.value = '';
                repoAddPicker.reset();
                showRepoMsg('Added ' + repo + ' - indexing...', 'info');
                await triggerReindex(false, true, parts[1]);
                loadRepos(); loadRepoFilter();
            } catch (err) { showRepoMsg(err.message, 'error'); }
        });

        // ---- Repo picker: suggestions from GitHub + existence check before submit ----
        function normalizeRepoInput(v) {
            return String(v || '').trim().replace(/^https?:[/][/]github[.]com[/]/, '').replace(/[.]git$/, '').replace(/[/]+$/, '');
        }
        function looksLikeRepo(v) { return /^[A-Za-z0-9_-][A-Za-z0-9_.-]*[/][A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(v); }
        let _ghRepoNames = null;
        function loadGhRepoNames() {
            if (!_ghRepoNames) {
                _ghRepoNames = api('/api/github/repos').then(r => (r && r.repos) || []).catch(err => { _ghRepoNames = null; throw err; });
            }
            return _ghRepoNames;
        }
        // opts.allowEmpty: an empty value is valid (clears the field), e.g. the wiki repo.
        function attachRepoPicker(input, submitBtn, opts = {}) {
            const wrap = document.createElement('div');
            wrap.className = 'picker';
            wrap.style.flex = input.style.flex;
            wrap.style.minWidth = input.style.minWidth;
            input.style.flex = ''; input.style.minWidth = '';
            input.parentNode.insertBefore(wrap, input);
            wrap.appendChild(input);
            const status = document.createElement('div');
            status.className = 'picker-status';
            const list = document.createElement('div');
            list.className = 'picker-list';
            list.style.display = 'none';
            wrap.append(status, list);
            let items = [], active = -1, timer = null, seq = 0;
            const current = () => normalizeRepoInput(input.value);
            const setSubmit = ok => { if (submitBtn) submitBtn.disabled = !ok; };
            const hideList = () => { list.style.display = 'none'; active = -1; };
            function setActive(i) {
                active = i;
                const els = list.querySelectorAll('.picker-item');
                els.forEach((el, j) => el.classList.toggle('active', j === i));
                if (els[i]) els[i].scrollIntoView({ block: 'nearest' });
            }
            async function openList() {
                let names;
                try { names = await loadGhRepoNames(); } catch (_) { hideList(); return; }
                const q = current().toLowerCase();
                items = names.filter(r => r.toLowerCase().includes(q));
                active = -1;
                if (!items.length) { hideList(); return; }
                list.innerHTML = items.map((r, i) => '<div class="picker-item" data-i="' + i + '">' + escapeHtml(r) + '</div>').join('');
                list.style.display = 'block';
            }
            function setStatus(text, ok, bad) {
                status.textContent = text;
                status.classList.toggle('bad', !!bad);
            }
            async function check(v) {
                const mine = ++seq;
                setSubmit(false);
                setStatus('checking...', false, false);
                try {
                    const r = await api('/api/github/repo-check?repo=' + encodeURIComponent(v));
                    if (mine !== seq || v !== current() || !r) return;
                    if (!r.exists) { setStatus('✗ not found', false, true); setSubmit(false); return; }
                    setStatus('✓ exists' + (r.private ? ' (private)' : '') + (r.archived ? ' (archived)' : ''), false, false);
                    setSubmit(true);
                } catch (err) {
                    // GitHub or the token is unavailable: let the user try anyway, the server reports the real error.
                    if (mine !== seq || v !== current()) return;
                    setStatus("⚠ can't check (" + err.message + ')', false, false);
                    setSubmit(true);
                }
            }
            function scheduleCheck() {
                clearTimeout(timer);
                seq++;
                const v = current();
                if (!v) { setStatus('', false, false); setSubmit(!!opts.allowEmpty); return; }
                // the already-saved value needs no GitHub round-trip and must stay saveable
                if (opts.saved && v === opts.saved) { setStatus('', false, false); setSubmit(true); return; }
                if (!looksLikeRepo(v)) { setStatus('', false, false); setSubmit(false); return; }
                setSubmit(false);
                timer = setTimeout(() => check(v), 400);
            }
            function pick(repo) {
                input.value = repo;
                hideList();
                clearTimeout(timer);
                check(current());
            }
            input.addEventListener('focus', openList);
            // Tab/blur closes the list; row picks use mousedown + preventDefault, so they never blur first
            input.addEventListener('blur', hideList);
            input.addEventListener('input', () => { openList(); scheduleCheck(); });
            input.addEventListener('keydown', e => {
                const open = list.style.display !== 'none' && items.length > 0;
                if (e.key === 'Escape' && open) { e.preventDefault(); hideList(); }
                else if (e.key === 'ArrowDown' && open) { e.preventDefault(); setActive((active + 1) % items.length); }
                else if (e.key === 'ArrowUp' && open) { e.preventDefault(); setActive(active <= 0 ? items.length - 1 : active - 1); }
                else if (e.key === 'Enter' && open && active >= 0) { e.preventDefault(); pick(items[active]); }
            });
            // mousedown keeps focus in the input; the click then picks the row.
            list.addEventListener('mousedown', e => {
                const it = e.target.closest('.picker-item');
                if (!it) return;
                e.preventDefault();
                pick(items[+it.dataset.i]);
            });
            // re-rendered panels drop their pickers: the listener removes itself once its wrapper is gone
            const onDocClick = e => {
                if (!wrap.isConnected) { document.removeEventListener('click', onDocClick); return; }
                if (!wrap.contains(e.target)) hideList();
            };
            document.addEventListener('click', onDocClick);
            scheduleCheck();
            return {
                reset() { clearTimeout(timer); seq++; hideList(); setStatus('', false, false); setSubmit(!!opts.allowEmpty); },
            };
        }
        const repoAddPicker = attachRepoPicker(document.getElementById('repo-add-input'), document.querySelector('#repo-add-form button[type=submit]'));

        function renderTokenStatus(info) {
            const el = document.getElementById('token-status');
            if (!info.set) { el.textContent = 'No token configured. Private repos cannot be listed or cloned.'; return; }
            const src = info.source === 'settings' ? 'dashboard setting' : 'GITHUB_TOKEN env var';
            let text = info.type + ' token ' + info.hint + ' from ' + src;
            if (info.login) text += ' - authenticated as ' + info.login;
            if (info.scopes && info.scopes.length) text += ' - scopes: ' + info.scopes.join(', ');
            if (info.error) text += ' - ERROR: ' + info.error;
            if (info.type === 'classic' && info.scopes && !info.scopes.includes('repo')) text += ' - missing repo scope (private repos will fail)';
            el.textContent = text;
        }
        async function loadTokenStatus() {
            try { renderTokenStatus(await api('/api/settings')); }
            catch (err) { document.getElementById('token-status').textContent = 'Error: ' + err.message; }
        }
        function showTokenMsg(msg, type) { toast(msg, type); }
        document.getElementById('token-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = document.getElementById('token-input');
            const token = input.value.trim();
            if (!token) return;
            try {
                const info = await api('/api/settings', { method: 'PUT', body: JSON.stringify({ github_token: token }) });
                input.value = '';
                renderTokenStatus(info);
                showTokenMsg('Saved. Used for the next repo list and reindex.', 'info');
            } catch (err) { showTokenMsg(err.message, 'error'); }
        });
        document.getElementById('token-clear').addEventListener('click', async () => {
            try { renderTokenStatus(await api('/api/settings', { method: 'DELETE' })); showTokenMsg('Cleared. Falling back to the env var.', 'info'); }
            catch (err) { showTokenMsg(err.message, 'error'); }
        });

        function showRepoMsg(msg, type) { toast(msg, type); }

        function toast(msg, type = 'info') {
            const t = document.createElement('div');
            t.className = 'toast ' + type;
            t.textContent = msg;
            document.getElementById('toasts').appendChild(t);
            setTimeout(() => t.classList.add('out'), type === 'error' ? 6000 : 3500);
            setTimeout(() => t.remove(), type === 'error' ? 6400 : 3900);
        }
        function confirmDialog(msg, okLabel = 'Confirm', danger = true) {
            return new Promise(resolve => {
                const m = document.getElementById('confirm-modal');
                const ok = m.querySelector('.cm-ok'), cancel = m.querySelector('.cm-cancel');
                m.querySelector('.cm-msg').textContent = msg;
                ok.textContent = okLabel;
                ok.className = 'cm-ok' + (danger ? ' danger' : '');
                const done = v => { m.style.display = 'none'; ok.onclick = cancel.onclick = m.onclick = null; resolve(v); };
                ok.onclick = () => done(true);
                cancel.onclick = () => done(false);
                m.onclick = e => { if (e.target === m) done(false); };
                m.style.display = 'flex';
                ok.focus();
            });
        }
        function copyBtn(text) {
            return '<button class="ib" data-copy="' + escapeHtml(text) + '" title="Copy ' + escapeHtml(text) + '"><svg class="ico"><use href="#i-copy"/></svg></button>';
        }
        function copyText(text) {
            const fallback = () => {
                const a = document.createElement('textarea'); a.value = text; document.body.appendChild(a); a.select();
                try { document.execCommand('copy'); toast('Copied'); } catch (_) { toast('Copy failed', 'error'); }
                a.remove();
            };
            if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => toast('Copied ' + (text.length > 60 ? text.slice(0, 57) + '...' : text)), fallback);
            else fallback();
        }
        document.addEventListener('click', e => { const b = e.target.closest('[data-copy]'); if (b) copyText(b.dataset.copy); });

        const connectCmd = 'claude mcp add cortex --transport sse ' + window.location.origin + '/sse';
        document.getElementById('connect-cmd').textContent = connectCmd;
        document.getElementById('connect-copy').addEventListener('click', () => copyText(connectCmd));

        document.getElementById('sign-out').addEventListener('click', async () => {
            if (!await confirmDialog('Sign out in this browser? You will see the login page next.', 'Sign out', false)) return;
            localStorage.removeItem('cortex_token');
            localStorage.removeItem('cortex_refresh');
            oauthStarted = false;
            startOAuthFlow();
        });

        // ---- Users & shared workspaces (admin) ----
        const enc = encodeURIComponent;
        let _wsNames = [];
        async function loadUsersPanel() {
            try {
                const [w, u] = await Promise.all([api('/api/workspaces'), api('/api/users')]);
                if (!w || !u) return;
                renderWorkspaces(w.workspaces || []);
                renderUsers(u.users || [], u.invites || []);
            } catch (err) { toast(err.message, 'error'); }
        }
        function updateInviteHint() {
            const ws = currentWs();
            document.getElementById('invite-hint').textContent = ws === 'default'
                ? 'joins no workspace (switch to a shared one first)' : 'joins ' + ws;
        }
        function renderWorkspaces(list) {
            _wsNames = list.map(w => w.name);
            updateInviteHint();
            const ws = currentWs();
            const sub = document.getElementById('ws-current-sub');
            const el = document.getElementById('ws-current');
            sub.textContent = ws;
            if (ws === 'default') {
                el.innerHTML = '<div class="hint">default is your private workspace: notes from your vault, code from the Repos tab.</div>';
                return;
            }
            const w = list.find(x => x.name === ws);
            // deleted meanwhile (e.g. by another tab): fall back to default instead of a dead card
            if (!w) { switchWs('default'); return; }
            const repos = (w.repos || []).map(r => {
                const name = r.split('/')[1];
                const err = (w.errors || {})[name];
                const ok = (w.indexed_at || {})[name];
                const title = err ? escapeHtml(err) : (ok ? 'indexed ' + timeAgo(ok) : 'not indexed yet');
                return '<span class="chip" title="' + title + '">' + (err ? '! ' : '') + escapeHtml(r) + '</span>';
            }).join('') || '<span class="hint">no code repos</span>';
            el.innerHTML =
                '<div class="hint">members: ' + escapeHtml((w.members || []).join(', ') || 'none') + '</div>' +
                '<form id="ws-cur-wiki-form" style="display:flex;gap:0.4rem;margin:0.6rem 0;align-items:center;flex-wrap:wrap"><span class="hint">wiki</span>' +
                '<input id="ws-cur-wiki" value="' + escapeHtml(w.wiki_repo || '') + '" placeholder="owner/name (notes)" autocomplete="off" style="flex:1;min-width:200px">' +
                '<button type="submit" id="ws-cur-wiki-save" class="secondary small">Save</button></form>' +
                '<div class="hint" style="margin-bottom:0.4rem">code repos (manage in the Repos tab):</div><div>' + repos + '</div>' +
                '<div style="display:flex;gap:0.5rem;margin-top:0.75rem"><button id="ws-cur-reindex" class="secondary small">Reindex</button>' +
                '<button id="ws-cur-del" class="danger small">Delete workspace</button></div>';
            attachRepoPicker(document.getElementById('ws-cur-wiki'), document.getElementById('ws-cur-wiki-save'), { allowEmpty: true, saved: w.wiki_repo || '' });
            document.getElementById('ws-cur-wiki-form').addEventListener('submit', e => {
                e.preventDefault();
                const val = normalizeRepoInput(document.getElementById('ws-cur-wiki').value);
                usersAction(() => api('/api/workspaces/' + enc(ws), { method: 'PUT', body: JSON.stringify({ wiki_repo: val }) }), 'Wiki saved. Reindex to pick it up.');
            });
            document.getElementById('ws-cur-reindex').addEventListener('click', () =>
                usersAction(() => api('/api/workspaces/' + enc(ws) + '/reindex', { method: 'POST', body: JSON.stringify({ notes: true, code: true }) }), 'Reindex queued for ' + ws));
            document.getElementById('ws-cur-del').addEventListener('click', async () => {
                if (!await confirmDialog('Delete workspace ' + ws + '? Members lose access; indexed data stays on disk.', 'Delete')) return;
                try {
                    await api('/api/workspaces/' + enc(ws), { method: 'DELETE' });
                    localStorage.setItem('cortex_ws', 'default');
                    location.reload();
                } catch (err) { toast(err.message, 'error'); }
            });
        }
        function renderUsers(users, invites) {
            const el = document.getElementById('user-list');
            let html = users.map(u => {
                const name = escapeHtml(u.username);
                if (u.admin) return '<div class="urow"><b>' + name + '</b><span class="hint">admin, all workspaces</span></div>';
                const chips = (u.workspaces || []).map(w => '<span class="chip">' + escapeHtml(w) +
                    '<button class="ib u-revoke" data-user="' + name + '" data-ws="' + escapeHtml(w) + '" title="Revoke"><svg class="ico"><use href="#i-trash"/></svg></button></span>').join('');
                const grantable = _wsNames.filter(w => !(u.workspaces || []).includes(w));
                const grant = grantable.length ? '<select class="u-grant-sel" data-user="' + name + '"><option value="">+ workspace</option>' +
                    grantable.map(w => '<option>' + escapeHtml(w) + '</option>').join('') + '</select>' : '';
                return '<div class="urow"><b>' + name + '</b><span>' + (chips || '<span class="hint">no workspaces</span>') + '</span>' + grant +
                    '<span style="margin-left:auto"><button class="ib u-del" data-user="' + name + '" title="Remove user"><svg class="ico"><use href="#i-trash"/></svg></button></span></div>';
            }).join('');
            html += invites.map(i => '<div class="urow"><b>' + escapeHtml(i.username) + '</b><span class="hint">invite pending (' +
                escapeHtml((i.workspaces || []).join(', ') || 'no workspaces') + '), expires ' + escapeHtml(i.expires_at.slice(0, 10)) + '</span>' +
                '<span style="margin-left:auto"><button class="ib u-del" data-user="' + escapeHtml(i.username) + '" title="Cancel invite"><svg class="ico"><use href="#i-trash"/></svg></button></span></div>').join('');
            el.innerHTML = html;
        }
        async function usersAction(fn, okMsg) {
            try { const r = await fn(); if (r === undefined) return; if (okMsg) toast(okMsg); loadUsersPanel(); }
            catch (err) { toast(err.message, 'error'); }
        }
        updateInviteHint();
        const wsWikiPicker = attachRepoPicker(document.getElementById('ws-wiki'), document.querySelector('#ws-create-form button[type=submit]'), { allowEmpty: true });
        document.getElementById('ws-create-form').addEventListener('submit', async e => {
            e.preventDefault();
            const name = document.getElementById('ws-name').value.trim();
            const wiki = normalizeRepoInput(document.getElementById('ws-wiki').value);
            try {
                await api('/api/workspaces', { method: 'POST', body: JSON.stringify({ name, wiki_repo: wiki }) });
            } catch (err) { toast(err.message, 'error'); return; }
            document.getElementById('ws-name').value = '';
            document.getElementById('ws-wiki').value = '';
            wsWikiPicker.reset();
            toast('Workspace ' + name + ' created');
            if (await confirmDialog('Switch to ' + name + ' now?', 'Switch', false)) switchWs(name);
            else { loadUsersPanel(); loadWsSwitcher(); }
        });
        document.getElementById('invite-form').addEventListener('submit', async e => {
            e.preventDefault();
            const username = document.getElementById('invite-name').value.trim();
            const ws = currentWs();
            const workspaces = ws === 'default' ? [] : [ws];
            try {
                const r = await api('/api/invites', { method: 'POST', body: JSON.stringify({ username, workspaces }) });
                if (!r) return;
                document.getElementById('invite-result').innerHTML = '<div class="hint" style="margin-top:0.6rem">Send this link to ' + escapeHtml(username) +
                    ' (shown once, single use, ' + r.expires_in_days + ' days):</div><div class="cmd"><code>' + escapeHtml(r.link) +
                    '</code><button class="ib" data-copy="' + escapeHtml(r.link) + '" title="Copy"><svg class="ico"><use href="#i-copy"/></svg></button></div>';
                document.getElementById('invite-name').value = '';
                loadUsersPanel();
            } catch (err) { toast(err.message, 'error'); }
        });
        document.getElementById('user-list').addEventListener('click', async e => {
            const rv = e.target.closest('.u-revoke');
            if (rv) usersAction(() => api('/api/users/' + enc(rv.dataset.user) + '/workspaces', { method: 'DELETE', body: JSON.stringify({ workspace: rv.dataset.ws }) }), 'Access revoked');
            const del = e.target.closest('.u-del');
            if (del && await confirmDialog('Remove ' + del.dataset.user + '? Their logins stop working immediately.', 'Remove'))
                usersAction(() => api('/api/users/' + enc(del.dataset.user), { method: 'DELETE' }), 'Removed ' + del.dataset.user);
        });
        document.getElementById('user-list').addEventListener('change', e => {
            const sel = e.target.closest('.u-grant-sel'); if (!sel || !sel.value) return;
            usersAction(() => api('/api/users/' + enc(sel.dataset.user) + '/workspaces', { method: 'POST', body: JSON.stringify({ workspace: sel.value }) }), 'Access granted');
        });

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
            // big graphs: label only the most central nodes until zoomed in (labels piled up on phones)
            const LABEL_TOP = 40;
            const ranked = [...data.nodes].sort((a, b) => (b.centrality || 0) - (a.centrality || 0));
            const keyLabel = new Set(data.nodes.length > LABEL_TOP ? ranked.slice(0, LABEL_TOP) : data.nodes);
            let labels = null;
            svg.call(d3.zoom().scaleExtent([0.1, 8]).on('zoom', e => {
                g.attr('transform', e.transform);
                if (labels) labels.attr('display', d => (e.transform.k >= 2 || keyLabel.has(d)) ? null : 'none');
            }));
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
            labels = node.append('text').attr('display', d => keyLabel.has(d) ? null : 'none').text(d=>{ const id=d.id||d.file||''; return id.split('/').pop().replace(/\\.(ts|tsx|js|jsx|py|kt|kts|svelte)$/,''); }).attr('font-size','8px').attr('fill','#8896a8').attr('text-anchor','middle').attr('dy',d=>r(d)+9).style('pointer-events','none').style('user-select','none');
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
        document.addEventListener('keydown', e => {
            if (e.key !== 'Escape') return;
            closeHistoryModal();
            const cm = document.getElementById('confirm-modal');
            if (cm.style.display === 'flex') cm.querySelector('.cm-cancel').click();
        });
    </script>
    <div id="toasts" aria-live="polite"></div>
    <div id="confirm-modal" class="modal"><div class="modal-box"><div class="cm-msg"></div><div class="cm-row"><button class="cm-cancel secondary">Cancel</button><button class="cm-ok">Confirm</button></div></div></div>
    <div id="history-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:1000;align-items:center;justify-content:center">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.5rem;width:90%;max-width:540px;max-height:80vh;overflow-y:auto">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">
          <span style="font-weight:700;font-size:0.95rem">Past versions</span>
          <button onclick="closeHistoryModal()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1.1rem;line-height:1">&#x2715;</button>
        </div>
        <table class="webhook-table" style="width:100%"><tbody id="history-modal-body"></tbody></table>
      </div>
    </div>
</body>
</html>"""

UI_HTML = _UI_TEMPLATE.replace("__LOGO__", LOGO_SVG)
