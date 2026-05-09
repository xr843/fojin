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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.elasticsearch import get_es
from app.database import get_db
from app.models.dictionary import DictionaryEntry
from app.models.hot_question import HotQuestion
from app.services.search import (
    search_content,
    search_semantic,
    search_texts,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])

_DICT_SECTION_LIMIT = 5
_HOT_Q_SECTION_LIMIT = 4


async def _dict_top_hits(db: AsyncSession, q: str) -> list[dict]:
    """Top-N exact + prefix dictionary hits for the unified result.

    Mirrors the /api/dictionary/search prioritization but caps tighter
    since this is a teaser, not a full results page.
    """
    relevance = case(
        (DictionaryEntry.headword == q, 3),
        (DictionaryEntry.headword.ilike(f"{q}%"), 2),
        else_=1,
    )
    stmt = (
        select(DictionaryEntry)
        .options(joinedload(DictionaryEntry.source))
        .where(or_(DictionaryEntry.headword == q, DictionaryEntry.headword.ilike(f"{q}%")))
        .order_by(relevance.desc(), func.length(DictionaryEntry.headword), DictionaryEntry.headword)
        .limit(_DICT_SECTION_LIMIT)
    )
    rows = await db.execute(stmt)
    out = []
    for e in rows.unique().scalars().all():
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


async def _hot_question_hits(db: AsyncSession, q: str) -> list[dict]:
    """Pre-curated hot_questions matching the query as substring.

    These are 200 hand-edited prompts that already exist in the system —
    surfacing them in unified results steers the 77 empty chat sessions /
    493 single-turn sessions toward a starting point.
    """
    stmt = (
        select(HotQuestion)
        .where(HotQuestion.is_active.is_(True))
        .where(HotQuestion.display_text.ilike(f"%{q}%"))
        .order_by(HotQuestion.sort_order.asc())
        .limit(_HOT_Q_SECTION_LIMIT)
    )
    rows = await db.execute(stmt)
    out = []
    for h in rows.scalars().all():
        out.append(
            {
                "slug": h.slug,
                "category": h.category,
                "text": h.display_text,
                "url": f"/chat?q={h.display_text}",
            }
        )
    return out


@router.get("/search/unified")
async def search_unified(
    q: str = Query(..., min_length=1, max_length=200, description="Unified search query"),
    sources: str | None = Query(None, description="Comma-separated source codes filter"),
    lang: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Run all search backends in parallel and return sectioned results.

    Returns:
        {
            "query": str,
            "sections": {
                "dictionary": [...]    # top-5 dict hits with /dict/ links
                "hot_questions": [...] # top-4 curated prompts
                "catalog": {...}       # SearchResponse — top-10 metadata hits
                "content": {...}       # ContentSearchResponse — top-5 body hits
                "semantic": {...}      # SemanticSearchResponse — top-5 vector hits
            },
            "errors": { section_name: error_string, ... }
        }
    """
    es = get_es()

    catalog_coro = search_texts(es, q, page=1, size=10, sources=sources, lang=lang, db=db)
    content_coro = search_content(es, q, page=1, size=5, sources=sources, lang=lang)
    semantic_coro = search_semantic(db, q, size=5, lang=lang, sources=sources)
    dict_coro = _dict_top_hits(db, q)
    hot_coro = _hot_question_hits(db, q)

    catalog_r, content_r, semantic_r, dict_r, hot_r = await asyncio.gather(
        catalog_coro,
        content_coro,
        semantic_coro,
        dict_coro,
        hot_coro,
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
    _attach("hot_questions", hot_r)

    return {"query": q, "sections": sections, "errors": errors}
