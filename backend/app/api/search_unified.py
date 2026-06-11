"""Unified search endpoint that fans out to all search backends in parallel.

Why this exists:
- /search returns metadata hits, /search/content returns body hits,
  /search/semantic returns RAG vector hits, /api/dictionary/search/grouped
  returns dictionary hits. Frontend currently runs them as separate React
  Query hooks per tab, forcing the user to choose "which kind of search"
  before seeing results.
- Real users (per Umami: /search PV 3,585/mo, #2 entry) just type a
  word — they don't know whether they want catalog vs content vs semantic.
- This endpoint runs all four in parallel and returns a sectioned response.
  The frontend can render a single unified result page or fall back to
  the per-backend tabs for advanced users.

Concurrency safety:
- Each backend has its own retry/timeout. We use asyncio.gather with
  return_exceptions so a single backend failure doesn't sink the whole
  response — the failed section just comes back empty with an
  ``error`` field set.
- Total wall time ≈ max of the slowest backend, not sum.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import joinedload

from app.core.elasticsearch import get_es
from app.database import async_session
from app.models.dictionary import DictionaryEntry
from app.services.search import (
    search_content,
    search_semantic,
    search_texts,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

_DICT_SECTION_LIMIT = 5


async def _dict_top_hits(q: str) -> list[dict]:
    """Top-N exact + prefix dictionary hits for the unified result.

    Mirrors the /api/dictionary/search prioritization but caps tighter
    since this is a teaser, not a full results page. Uses its own session
    so it can run concurrently with other DB-using sections in
    asyncio.gather (a single AsyncSession does not allow concurrent
    operations).
    """
    relevance = case(
        (DictionaryEntry.headword == q, 3),
        (DictionaryEntry.headword.ilike(f"{q}%"), 2),
        else_=1,
    )
    async with async_session() as db:
        stmt = (
            select(DictionaryEntry)
            .options(joinedload(DictionaryEntry.source))
            .where(or_(DictionaryEntry.headword == q, DictionaryEntry.headword.ilike(f"{q}%")))
            .order_by(relevance.desc(), func.length(DictionaryEntry.headword), DictionaryEntry.headword)
            .limit(_DICT_SECTION_LIMIT)
        )
        rows = await db.execute(stmt)
        entries = list(rows.unique().scalars().all())

    out = []
    for e in entries:
        out.append(
            {
                "id": e.id,
                "headword": e.headword,
                "reading": e.reading,
                "definition": (e.definition or "")[:200],
                "source": e.source.name_zh if e.source else None,
                "url": f"/dict/{e.headword}",
            }
        )
    return out


@router.get("/search/unified")
async def search_unified(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200, description="Unified search query"),
    sources: str | None = Query(None, description="Comma-separated source codes filter"),
    lang: str | None = Query(None),
):
    """Run all search backends in parallel and return sectioned results.

    Returns:
        {
            "query": str,
            "sections": {
                "dictionary": [...]    # top-5 dict hits with /dict/ links
                "catalog": {...}       # SearchResponse — top-10 metadata hits
                "content": {...}       # ContentSearchResponse — top-5 body hits
                "semantic": {...}      # SemanticSearchResponse — top-5 vector hits
            },
            "errors": { section_name: error_string, ... }
        }
    """
    es = get_es()

    # EVERY db-touching section opens its own session: a single AsyncSession
    # cannot service two concurrent execute() calls, and under gather() the
    # loser dies with "session is provisioning a new connection; concurrent
    # operations are not permitted" — which _attach silently swallowed,
    # rendering the catalog section (with the base-text top hit) as null
    # while commentaries from the content section still displayed. catalog
    # only needs db for the related-translations enrich; semantic needs it
    # for pgvector. The request-scoped Depends(get_db) is gone entirely so
    # this endpoint no longer pins a pool connection for its whole lifetime.
    gaiji_normalizer = getattr(request.app.state, "gaiji_normalizer", None)

    async def catalog_coro():
        async with async_session() as session:
            return await search_texts(
                es, q, page=1, size=10, sources=sources, lang=lang, db=session
            )

    async def semantic_coro():
        async with async_session() as session:
            return await search_semantic(session, q, size=5, lang=lang, sources=sources)

    content_coro = search_content(
        es, q, page=1, size=5, sources=sources, lang=lang, gaiji_normalizer=gaiji_normalizer
    )
    dict_coro = _dict_top_hits(q)

    catalog_r, content_r, semantic_r, dict_r = await asyncio.gather(
        catalog_coro(),
        content_coro,
        semantic_coro(),
        dict_coro,
        return_exceptions=True,
    )

    sections: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def _attach(name: str, result: Any, on_ok=lambda r: r):
        if isinstance(result, Exception):
            logger.warning("unified search section %s failed: %s", name, result)
            errors[name] = str(result)
            sections[name] = None
        else:
            sections[name] = on_ok(result)

    _attach(
        "catalog",
        catalog_r,
        on_ok=lambda r: {
            "total": r.total,
            "results": [hit.model_dump() for hit in r.results],
        },
    )
    _attach("content", content_r)
    _attach(
        "semantic",
        semantic_r,
        on_ok=lambda r: {
            "total": r.total,
            "results": [hit.model_dump() for hit in r.results],
        },
    )
    _attach("dictionary", dict_r)

    return {"query": q, "sections": sections, "errors": errors}
