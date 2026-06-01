FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Tree-sitter grammars first — slow C compilation, rarely changes -> high cache hit rate
COPY mcp/requirements-ts.txt .
RUN pip install --no-cache-dir -r requirements-ts.txt

# Fast installs, changes more often
COPY mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION /app/VERSION
COPY mcp/server.py mcp/web_ui.py mcp/oauth.py mcp/config.py mcp/reindex.py mcp/tools.py \
     mcp/template.py mcp/state.py mcp/repos.py mcp/onboarding.py \
     mcp/middleware.py mcp/watcher.py mcp/routes.py ./
COPY indexer/index.py indexer/index_code.py indexer/graph.py indexer/code_graph.py indexer/notes_graph.py indexer/global_graph.py indexer/chunker.py indexer/cache.py ./
RUN chmod +x /app/index.py /app/index_code.py
CMD ["python", "server.py"]
