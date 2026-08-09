# fojin MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes **fojin's verified
cross-canon Buddhist corpus** to any MCP client (Claude Desktop, ChatGPT,
research tooling). It turns fojin from "an app you visit" into **infrastructure
an AI can call** — every passage it returns carries a portable, resolvable
citation (`fojin:cbeta/T0251.1`), so a model can ground and deep-link its claims
instead of inventing scripture.

Read-only by construction: it only issues GETs against fojin's public API.

Two ways to use it:

1. **Hosted endpoint (zero install)** — `https://mcp.fojin.ai/mcp`, streamable
   HTTP, anonymous, rate-limited. One line in Claude Code:

   ```bash
   claude mcp add --transport http fojin https://mcp.fojin.ai/mcp
   ```

2. **Local over stdio** — `uvx fojin-mcp`, the classic MCP install (below).

## Tools

| Tool | What it returns |
|------|-----------------|
| `search_corpus(query, limit, lang)` | Semantic search hits, each with a `urn`, title, snippet, score |
| `read_passage(text_id, juan_num)` | The actual content of one fascicle (卷) + its `urn` |
| `get_parallels(text_id, juan_num)` | Cross-canon aligned parallels (Chinese↔Pali↔Tibetan), each with a `urn` and deep-link `reader_ref` — the alignment moat |
| `lookup_dictionary(term, limit)` | Entries across fojin's 32 dictionaries |
| `lookup_entity(query, limit)` | Knowledge-graph entities (people, places, works, terms) |
| `resolve_urn(urn)` | Resolve/verify a `fojin:` URN → reader URL + existence |

Every result that names a canonical passage carries a **`urn`** — fojin's stable
cross-canon identifier, interoperable with CBETA / SuttaCentral (`sc/`) / 84000
(`84k/toh`) / GRETIL / VRI numbering. Pass it back to `resolve_urn`, or cite it
directly.

## Install & run

Once published to PyPI, no clone needed — run it with `uvx` (nothing to
install) or `pip`:

```bash
uvx fojin-mcp                 # zero-install, stdio transport (the MCP default)
# or
pip install fojin-mcp && fojin-mcp
```

From a checkout (development):

```bash
cd mcp-server && pip install -e . && python -m fojin_mcp
```

By default it talks to `https://fojin.app/api`. Point it elsewhere (self-host,
staging) with an env var:

```bash
FOJIN_API_BASE_URL=http://localhost:8000/api uvx fojin-mcp
```

### Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "fojin": {
      "command": "uvx",
      "args": ["fojin-mcp"]
    }
  }
}
```

(or `"command": "fojin-mcp"` if you `pip install`ed it, or `python -m fojin_mcp`
from a checkout.) Restart Claude Desktop; the six fojin tools then appear.

### ChatGPT / other MCP clients

Any client that speaks MCP over stdio can launch `uvx fojin-mcp` (or the
`fojin-mcp` console script); any client that speaks streamable HTTP can point
at `https://mcp.fojin.ai/mcp`. Both discover the six tools automatically.

## Hosting the HTTP endpoint (self-host)

The same package serves streamable HTTP (requires the `http` extra, which adds
uvicorn):

```bash
pip install 'fojin-mcp[http]'
fojin-mcp --transport streamable-http --port 8765 --public-host mcp.example.com
```

The hosted mode is **stateless JSON request/response** (`stateless_http` +
`json_response`): every tool call is one plain POST — no SSE streams, so it
sits safely behind Cloudflare's proxy and behind multi-worker uvicorn. It adds:

- **Per-client rate limiting** — sliding window keyed on `CF-Connecting-IP` /
  `X-Real-IP` (falling back to the socket peer). Tune with
  `--rate-limit`/`--rate-window` or `FOJIN_MCP_RATE_LIMIT`/`FOJIN_MCP_RATE_WINDOW`.
- **Host-header validation** (DNS-rebinding protection) pinned to
  `--public-host` / `FOJIN_MCP_PUBLIC_HOSTS` (default `mcp.fojin.ai`).
- **Access + tool logs** — one JSON line per request (`fojin_mcp.access`) and
  per tool call (`fojin_mcp.tools`) on stdout/stderr.
- **`/healthz`** for container/proxy healthchecks.

The production deployment is the `mcp` service in the repo's
`docker-compose.yml` (it talks to the backend container directly) plus the
`mcp.fojin.ai` server block in `deploy/host-nginx/fojin.conf`.

## Design

- **Standalone.** Talks to fojin only over HTTP; it does not import the backend,
  so it installs and runs independently (deps: `mcp`, `httpx`).
- **URNs built client-side.** fojin's search/read/alignment endpoints expose
  `cbeta_id`; the server builds the `urn` from it (`fojin_mcp/urn.py`, a vendored
  copy of the backend's `build_urn`, kept behaviourally identical and
  round-trip-tested). So citations work today, independent of any server change.
  `get_parallels` enriches each parallel's URN via a bounded, concurrent,
  best-effort `text_id → cbeta_id` lookup (a miss just leaves `urn: null`).
- **Testable core.** All HTTP + reshaping lives in `client.py` and is tested
  against a mocked transport; `server.py` is a thin MCP wiring layer (SDK v2 —
  `mcp>=2` is required; 2.0 removed the 1.x module this package imported
  through 0.1.0), and the hosted-edge concerns live in `http.py`.
- **Fails soft.** An upstream error returns `{"error": "..."}` to the model
  rather than crashing the tool call.

## Test

```bash
pip install -e '.[dev]'
pytest -q          # unit tests (no network)
```

## Publishing (maintainer)

CI (`.github/workflows/mcp-server.yml`) lints, tests, and builds the package on
every change under `mcp-server/`. To release to PyPI, bump `version` in
`pyproject.toml`, then push a tag:

```bash
git tag mcp-v0.2.0 && git push origin mcp-v0.2.0
```

`.github/workflows/mcp-publish.yml` builds and uploads. It needs credentials
once — set up **either** PyPI Trusted Publishing (recommended; no secret) for
project `fojin-mcp` / repo `xr843/fojin` / workflow `mcp-publish.yml` /
environment `pypi`, **or** a `PYPI_API_TOKEN` repo secret (then uncomment the
`password:` line in the workflow).

## License

Apache-2.0 (same as fojin).
