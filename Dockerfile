FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for tree-sitter native builds and igraph
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install runtime deps before copying source so layer caches
COPY pyproject.toml ./
RUN pip install --upgrade pip \
 && pip install \
        "kuzu==0.11.3" \
        "tree-sitter>=0.25.0" \
        "tree-sitter-python>=0.25.0" \
        "tree-sitter-javascript>=0.25.0" \
        "tree-sitter-typescript>=0.23.0" \
        "tree-sitter-java>=0.23.0" \
        "tree-sitter-go>=0.25.0" \
        "tree-sitter-rust>=0.24.0" \
        "tree-sitter-c>=0.24.0" \
        "tree-sitter-cpp>=0.23.0" \
        "igraph>=1.0.0" \
        "mcp>=1.0.0"

# Then copy source
COPY . .
RUN pip install -e .

# Renderer + MCP server default ports
EXPOSE 8765

# Default entry: MCP server (most common headless use)
# Override with: docker run ... python -m Code_Organism /path/to/project
CMD ["python", "-m", "Code_Organism.mcp_server"]
