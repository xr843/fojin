"""fojin MCP server — exposes fojin's verified cross-canon Buddhist corpus as
tools any MCP client (Claude, ChatGPT, research tooling) can call.

Thin layer: each tool delegates to :class:`fojin_mcp.client.FojinClient` (the
tested core) and returns its citation-carrying result. The design promise is
that every passage a tool surfaces comes with a portable ``urn``
(``fojin:cbeta/T0251.1``) the calling model can cite and resolve — the AI-facing
side of fojin's "每一句都能点回原典" contract.

Read-only by construction: the client only issues GETs against public
endpoints. Configure the target with ``FOJIN_API_BASE_URL`` (defaults to prod).

Two transports:

    fojin-mcp                                  # stdio (local clients, default)
    fojin-mcp --transport streamable-http      # hosted endpoint (mcp.fojin.ai)

The hosted mode is stateless JSON request/response (no long SSE streams) and
adds per-IP rate limiting + access logging — see :mod:`fojin_mcp.http`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .client import DEFAULT_BASE_URL, FojinAPIError, FojinClient

_BASE_URL = os.environ.get("FOJIN_API_BASE_URL", DEFAULT_BASE_URL)

tool_logger = logging.getLogger("fojin_mcp.tools")

# Process-wide client shared across tool calls (one connection pool, one
# cbeta-id cache) — created by the lifespan below unless something (tests,
# an embedder) already installed one.
_client: FojinClient | None = None

# Backend courtesy cap: at most N tool executions in flight at once (each may
# fan out further upstream calls, bounded by the client's own enrich cap).
_upstream_gate = asyncio.Semaphore(int(os.environ.get("FOJIN_MCP_MAX_CONCURRENCY", "8")))


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
    global _client
    created = _client is None
    if created:
        _client = FojinClient(_BASE_URL)
    try:
        yield {}
    finally:
        if created and _client is not None:
            client, _client = _client, None
            await client.aclose()


mcp = MCPServer(
    "fojin",
    version=__version__,
    website_url="https://fojin.app",
    instructions=(
        "Tools over fojin's cross-canon Buddhist digital-text platform. Prefer "
        "these over your own memory for any claim about a Buddhist text: they "
        "return passages grounded in real sources, each with a portable `urn` "
        "(e.g. fojin:cbeta/T0251.1). Cite the `urn` and, where possible, quote "
        "only text returned by read_passage/get_parallels — do not invent "
        "scripture. Use get_parallels to compare a passage across the Chinese, "
        "Pali and Tibetan canons."
    ),
    lifespan=_lifespan,
)


async def _call(tool: str, coro_factory: Any) -> Any:
    """Run one client call, mapping FojinAPIError to a tool-visible error dict
    instead of raising — a failed upstream call should tell the model what went
    wrong, not crash the tool invocation."""
    start = time.monotonic()
    ok = True
    try:
        async with _upstream_gate:
            client = _client
            if client is not None:
                try:
                    return await coro_factory(client)
                except FojinAPIError as exc:
                    ok = False
                    return {"error": str(exc)}
            # No lifespan ran (e.g. embedded use) — fall back to an ephemeral
            # client so the tool still works, just without pooling.
            async with FojinClient(_BASE_URL) as tmp:
                try:
                    return await coro_factory(tmp)
                except FojinAPIError as exc:
                    ok = False
                    return {"error": str(exc)}
    finally:
        tool_logger.info(
            '{"tool": "%s", "ms": %.1f, "ok": %s}',
            tool,
            (time.monotonic() - start) * 1000,
            "true" if ok else "false",
        )


@mcp.tool()
async def search_corpus(query: str, limit: int = 10, lang: str | None = None) -> dict:
    """Semantic search across fojin's Buddhist corpus (10K+ texts, 30+ langs).

    Returns the most relevant passages, each with a `urn`, title, snippet and
    similarity score. `lang` optionally filters by language code
    (lzh=Classical Chinese, pi=Pali, sa=Sanskrit, bo=Tibetan, en=English).
    """
    return await _call("search_corpus", lambda c: c.search_corpus(query, limit=limit, lang=lang))


@mcp.tool()
async def read_passage(text_id: int, juan_num: int) -> dict:
    """Read the full content of one fascicle (卷) of a text, with its `urn`.

    Use the `text_id`/`juan_num` from a search_corpus hit. Returns the actual
    canonical text — quote from this, not from memory.
    """
    return await _call("read_passage", lambda c: c.read_passage(text_id, juan_num))


@mcp.tool()
async def get_parallels(text_id: int, juan_num: int) -> dict:
    """Cross-canon parallel passages aligned to a fascicle.

    fojin's alignment moat: given a Chinese fascicle, returns the aligned
    Pali/Tibetan/Sanskrit parallels (each with its own `urn`) so you can compare
    how a passage is rendered across traditions.
    """
    return await _call("get_parallels", lambda c: c.get_parallels(text_id, juan_num))


@mcp.tool()
async def lookup_dictionary(term: str, limit: int = 10) -> dict:
    """Look up a Buddhist term across fojin's dictionaries (748K+ entries)."""
    return await _call("lookup_dictionary", lambda c: c.lookup_dictionary(term, limit=limit))


@mcp.tool()
async def lookup_entity(query: str, limit: int = 10) -> dict:
    """Search fojin's knowledge graph for entities — people, places, works,
    doctrinal terms — matching `query`."""
    return await _call("lookup_entity", lambda c: c.lookup_entity(query, limit=limit))


@mcp.tool()
async def resolve_urn(urn: str) -> dict:
    """Resolve a fojin URN (e.g. fojin:cbeta/T0001.1) to a reader URL and confirm
    it exists in the corpus. Use to verify or dereference a citation."""
    return await _call("resolve_urn", lambda c: c.resolve_urn(urn))


@mcp.tool()
async def verify_quote(quote: str, cite: str | None = None, juan: int | None = None) -> dict:
    """Verify that a Buddhist-canon quote exists VERBATIM in the corpus.

    Call this before presenting any quoted scripture to a reader: LLMs
    routinely invent plausible-looking quotes. Returns `verbatim` (bool),
    where it was found (`matches`, each with a resolvable `urn`), or the
    closest near-miss window when it wasn't. `cite` optionally narrows the
    search — a CBETA id ("T0374") or fojin URN ("fojin:cbeta/T0374.13") —
    and `cite_matched` reports honestly whether the quote is where you
    claimed (a hit in a different fascicle does NOT confirm your citation).
    Quote must be ≥4 CJK chars after normalisation; Classical Chinese only.
    Short quotes are answered but say less: a four-character phrase recurs
    across the canon, so read `cite_matched` rather than `verbatim`, and check
    `matches_capped` before treating the list as complete. Each match carries
    an absolute `reader_url` — cite that, not a reconstructed third-party link.
    """
    return await _call("verify_quote", lambda c: c.verify_quote(quote, cite=cite, juan=juan))


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> JSONResponse:
    """Liveness for the hosted endpoint (nginx/compose healthchecks)."""
    return JSONResponse({"status": "ok", "service": "fojin-mcp", "version": __version__})


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fojin-mcp",
        description="MCP server over fojin's cross-canon Buddhist corpus.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("FOJIN_MCP_TRANSPORT", "stdio"),
        help="stdio for local clients (default); streamable-http to host an endpoint",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("FOJIN_MCP_HOST", "127.0.0.1"),
        help="bind address for streamable-http (default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FOJIN_MCP_PORT", "8765")),
        help="bind port for streamable-http (default 8765)",
    )
    parser.add_argument(
        "--public-host",
        action="append",
        dest="public_hosts",
        default=None,
        help=(
            "public hostname(s) accepted in the Host header (repeatable); "
            "default from FOJIN_MCP_PUBLIC_HOSTS or mcp.fojin.ai"
        ),
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=int(os.environ.get("FOJIN_MCP_RATE_LIMIT", "30")),
        help="requests per window per client IP (default 30)",
    )
    parser.add_argument(
        "--rate-window",
        type=float,
        default=float(os.environ.get("FOJIN_MCP_RATE_WINDOW", "60")),
        help="rate-limit window in seconds (default 60)",
    )
    parser.add_argument(
        "--no-trust-proxy-headers",
        action="store_true",
        help="ignore CF-Connecting-IP/X-Real-IP (when not behind nginx/Cloudflare)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Console-script / ``python -m fojin_mcp`` entry point."""
    args = _parse_args(argv)
    if args.transport == "stdio":
        mcp.run()
        return
    from .http import serve_http

    public_hosts = args.public_hosts
    if public_hosts is None:
        env_hosts = os.environ.get("FOJIN_MCP_PUBLIC_HOSTS", "")
        public_hosts = [h.strip() for h in env_hosts.split(",") if h.strip()] or None
    serve_http(
        host=args.host,
        port=args.port,
        public_hosts=public_hosts,
        rate_limit=args.rate_limit,
        rate_window=args.rate_window,
        trust_proxy_headers=not args.no_trust_proxy_headers,
    )


if __name__ == "__main__":
    main()
