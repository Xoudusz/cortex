#!/usr/bin/env node
'use strict';

const { spawnSync } = require('child_process');

function which(cmd) {
  const r = spawnSync('which', [cmd], { encoding: 'utf8' });
  return r.status === 0 ? r.stdout.trim() : null;
}

function mcpList() {
  const claude = which('claude');
  if (!claude) return '';
  const r = spawnSync(claude, ['mcp', 'list'], { encoding: 'utf8', timeout: 5000 });
  return r.stdout || '';
}

function emit(msg) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'SessionStart',
      additionalContext: msg,
    },
  }));
}

const registered = mcpList().includes('cortex');

if (registered) {
  emit('[cortex] connected — search_code, search_notes, get_neighbors, get_community, reindex ready');
  process.exit(0);
}

const cortexBin = which('cortex');

if (!cortexBin) {
  emit('[cortex] not installed. Run: pipx install cortex-local && cortex install');
  process.exit(0);
}

// Binary found but MCP not registered — run cortex install
const result = spawnSync(cortexBin, ['install'], {
  encoding: 'utf8',
  timeout: 60000,
});

if (result.status === 0) {
  emit('[cortex] MCP registered. Restart Claude Code to activate search tools.');
} else {
  const err = (result.stderr || result.stdout || 'unknown error').trim().split('\n')[0];
  emit(`[cortex] auto-install failed: ${err}\nRun manually: cortex install`);
}
