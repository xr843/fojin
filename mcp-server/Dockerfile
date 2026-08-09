# Hosted fojin-mcp (mcp.fojin.ai) — streamable-HTTP MCP endpoint.
# The stdio install path for end users stays PyPI (`uvx fojin-mcp`); this
# image only exists so docker-compose can run the hosted endpoint.
FROM python:3.12-slim

WORKDIR /srv/fojin-mcp

# Package metadata + source only; tests/CI never enter the image.
COPY pyproject.toml README.md ./
COPY fojin_mcp ./fojin_mcp

RUN pip install --no-cache-dir ".[http]" && \
    useradd --system --no-create-home fojin-mcp

USER fojin-mcp

EXPOSE 8765

# --host 0.0.0.0 is container-internal only: compose publishes the port
# bound to the host's loopback, nginx/Cloudflare are the public path.
CMD ["fojin-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"]
