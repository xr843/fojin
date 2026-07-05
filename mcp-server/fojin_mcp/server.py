"""fojin MCP server — exposes fojin's verified cross-canon Buddhist corpus as
tools any MCP client (Claude, ChatGPT, research tooling) can call.

Thin layer: each tool delegates to :class:`fojin_mcp.client.FojinClient` (the
tested core) and returns its citation-carrying result. The design promise is
that every passage a tool surfaces comes with a portable ``urn``
(``fojin:cbeta/T0251.1``) the calling model can cite and resolve — the AI-facing
side of fojin's "每一句都能点回原典" contract.

Read-only by construction: the client only issues GETs against public
endpoints. Configure the target with ``FOJIN_API_BASE_URL`` (defaults to prod).

Run over stdio (the default MCP transport):

    python -m fojin_mcp
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import DEFAULT_BASE_URL, FojinAPIError, FojinClient

_BASE_URL = os.environ.get("FOJIN_API_BASE_URL", DEFAULT_BASE_URL)

mcp = FastMCP(
    "fojin",
    instructions=(
        "Tools over fojin's cross-canon Buddhist digital-text platform. Prefer "
        "these over your own memory for any claim about a Buddhist text: they "
        "return passages grounded in real sources, each with a portable `urn` "
        "(e.g. fojin:cbeta/T0251.1). Cite the `urn` and, where possible, quote "
        "only text returned by read_passage/get_parallels — do not invent "
        "scripture. Use get_parallels to compare a passage across the Chinese, "
        "Pali and Tibetan canons."
    ),
)


async def _call(coro_factory: Any) -> Any:
    """Run one client call, mapping FojinAPIError to a tool-visible error dict
    instead of raising — a failed upstream call should tell the model what went
    wrong, not crash the tool invocation."""
    async with FojinClient(_BASE_URL) as client:
        try:
            return await coro_factory(client)
        except FojinAPIError as exc:
            return {"error": str(exc)}


@mcp.tool()
async def search_corpus(query: str, limit: int = 10, lang: str | None = None) -> dict:
    """Semantic search across fojin's Buddhist corpus (10K+ texts, 30+ langs).

    Returns the most relevant passages, each with a `urn`, title, snippet and
    similarity score. `lang` optionally filters by language code
    (lzh=Classical Chinese, pi=Pali, sa=Sanskrit, bo=Tibetan, en=English).
    """
    return await _call(lambda c: c.search_corpus(query, limit=limit, lang=lang))


@mcp.tool()
async def read_passage(text_id: int, juan_num: int) -> dict:
    """Read the full content of one fascicle (卷) of a text, with its `urn`.

    Use the `text_id`/`juan_num` from a search_corpus hit. Returns the actual
    canonical text — quote from this, not from memory.
    """
    return await _call(lambda c: c.read_passage(text_id, juan_num))


@mcp.tool()
async def get_parallels(text_id: int, juan_num: int) -> dict:
    """Cross-canon parallel passages aligned to a fascicle.

    fojin's alignment moat: given a Chinese fascicle, returns the aligned
    Pali/Tibetan/Sanskrit parallels (each with its own `urn`) so you can compare
    how a passage is rendered across traditions.
    """
    return await _call(lambda c: c.get_parallels(text_id, juan_num))


@mcp.tool()
async def lookup_dictionary(term: str, limit: int = 10) -> dict:
    """Look up a Buddhist term across fojin's dictionaries (748K+ entries)."""
    return await _call(lambda c: c.lookup_dictionary(term, limit=limit))


@mcp.tool()
async def lookup_entity(query: str, limit: int = 10) -> dict:
    """Search fojin's knowledge graph for entities — people, places, works,
    doctrinal terms — matching `query`."""
    return await _call(lambda c: c.lookup_entity(query, limit=limit))


@mcp.tool()
async def resolve_urn(urn: str) -> dict:
    """Resolve a fojin URN (e.g. fojin:cbeta/T0001.1) to a reader URL and confirm
    it exists in the corpus. Use to verify or dereference a citation."""
    return await _call(lambda c: c.resolve_urn(urn))


def main() -> None:
    """Console-script / ``python -m fojin_mcp`` entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
