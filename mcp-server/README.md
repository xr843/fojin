# fojin MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes **fojin's verified
cross-canon Buddhist corpus** to any MCP client (Claude Desktop, ChatGPT,
research tooling). It turns fojin from "an app you visit" into **infrastructure
an AI can call** — every passage it returns carries a portable, resolvable
citation (`fojin:cbeta/T0251.1`), so a model can ground and deep-link its claims
instead of inventing scripture.

Read-only by construction: it only issues GETs against fojin's public API.

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

```bash
cd mcp-server
pip install -e .
python -m fojin_mcp          # stdio transport (the MCP default)
```

By default it talks to `https://fojin.app/api`. Point it elsewhere (self-host,
staging) with an env var:

```bash
FOJIN_API_BASE_URL=http://localhost:8000/api python -m fojin_mcp
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fojin": {
      "command": "python",
      "args": ["-m", "fojin_mcp"]
    }
  }
}
```

(or use the installed `fojin-mcp` console script as `"command"`.)

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
  against a mocked transport; `server.py` is a thin FastMCP wiring layer.
- **Fails soft.** An upstream error returns `{"error": "..."}` to the model
  rather than crashing the tool call.

## Test

```bash
pip install -e '.[dev]'
pytest -q          # unit tests (no network)
```

## License

Apache-2.0 (same as fojin).
