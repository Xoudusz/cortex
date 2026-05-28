FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Tree-sitter grammars first — slow C compilation, rarely changes -> high cache hit rate
COPY mcp/requirements-ts.txt .
RUN pip install --no-cache-dir -r requirements-ts.txt

# Fast installs, changes more often
COPY mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp/server.py mcp/web_ui.py .
COPY indexer/index.py indexer/index_code.py indexer/graph.py .
CMD ["python", "server.py"]
