# Stage 1: Build Roslyn C# analyzer (self-contained single-file binary)
FROM mcr.microsoft.com/dotnet/sdk:8.0-slim AS roslyn-builder
WORKDIR /build
COPY core/roslyn_tool/ .
RUN dotnet publish -c Release -r linux-x64 --self-contained true \
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o /out

# Stage 2: Python app
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Tree-sitter grammars first — slow C compilation, rarely changes -> high cache hit rate
COPY server/mcp/requirements-ts.txt .
RUN pip install --no-cache-dir -r requirements-ts.txt

# Fast installs, changes more often
COPY server/mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python3 -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')" || true

COPY VERSION /app/VERSION
COPY server/mcp/server.py server/mcp/web_ui.py server/mcp/oauth.py server/mcp/config.py server/mcp/reindex.py server/mcp/tools.py \
     server/mcp/tools_search.py server/mcp/tools_admin.py \
     server/mcp/template.py server/mcp/state.py server/mcp/repos.py server/mcp/onboarding.py \
     server/mcp/middleware.py server/mcp/watcher.py server/mcp/routes.py ./
COPY core/chunker.py core/cache.py core/graph.py core/code_graph.py core/notes_graph.py core/global_graph.py core/formatters.py core/roslyn_analyzer.py ./
COPY server/indexer/index.py server/indexer/index_code.py ./
COPY --from=roslyn-builder /out/CortexAnalyzer /app/roslyn_tool/CortexAnalyzer
RUN chmod +x /app/roslyn_tool/CortexAnalyzer /app/index.py /app/index_code.py
ENV ROSLYN_ANALYZER=/app/roslyn_tool/CortexAnalyzer
CMD ["python", "server.py"]
