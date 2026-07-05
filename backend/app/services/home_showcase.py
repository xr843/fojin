"""Dynamic homepage showcase — the live content behind the 6 hero feature cards.

The hero cards used to repeat the top nav verbatim (same icon, title, and
destination), differentiated only by a static example line. This service makes
them a *showcase* the nav can't be: each card's subtitle is real, rotating
platform content — live counts, a hot question, a dictionary term, a knowledge-
graph triple, geography. The 经典专题 card is driven by the frontend's own
collection content, so it isn't included here.

Two hard constraints, both honoured:
  - **Cheap**: this is the highest-traffic page. One Redis-cached aggregate
    (SHOWCASE_TTL) instead of six per-card fetches; every DB query is bounded.
  - **Degrades independently**: each card's data is best-effort — a failed or
    empty sub-query yields ``None`` for that card only (the frontend then shows
    its static fallback), and the whole endpoint never fails the page.

"Rotation" uses a time-bucketed seed so the showcase changes across cache
periods (feels alive) while staying stable within one (cacheable).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.dictionary import HOT_TERMS
from app.models.dictionary import DictionaryEntry
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.text import BuddhistText
from app.services.hot_questions import get_hot_questions

logger = logging.getLogger(__name__)

# Cache TTL for the whole aggregate, and the rotation bucket size. 15 min keeps
# the homepage lively without hammering the DB.
SHOWCASE_TTL = 900
_SHOWCASE_CACHE_KEY = "home:showcase:v2"  # v2: pools (not single picks)

# A small candidate pool size for rotation-by-seed queries: fetch a bounded set
# cheaply, then pick one deterministically per time bucket.
_POOL = 12
_GEO_TYPES = ("place", "monastery")

# Max chars of a dictionary definition shown on the card — kept short so the
# subtitle stays ~2 lines (the CSS also hard-clamps to 2 lines as a backstop).
_DEF_MAX_CHARS = 24

# Human-readable Chinese labels for the KG predicate vocabulary, so the card
# reads "智昇 → 活跃于 → 唐" instead of a raw "active_in" machine code. Covers the
# full predicate set in the graph; an unmapped predicate falls back to itself.
_PREDICATE_LABELS = {
    "teacher_of": "授学",
    "translated": "译",
    "translated_at": "译于",
    "alt_translation": "异译",
    "cites": "引",
    "commentary_on": "注",
    "associated_with": "关联",
    "active_in": "活跃于",
    "member_of_school": "属",
}


# Each card returns a POOL of candidates (cached SHOWCASE_TTL); the frontend
# picks one at random on every page load, so the card varies per refresh while
# the DB work stays cached. Pool sizes are small — enough variety, tiny payload.
_CHAT_POOL = 8
_GEO_POOL = 8


def _short_gloss(definition: str | None) -> str | None:
    """Trim a dictionary definition to a short card-sized gloss.

    Classical-Chinese definitions run long and multi-clause; on the card we want
    at most ~一句. Take up to the first sentence break, then hard-cap the chars,
    appending an ellipsis when truncated. Returns None for an empty definition so
    the card shows just the term."""
    text = (definition or "").strip().replace("\n", " ")
    if not text:
        return None
    # Prefer cutting at the first sentence/clause boundary if it lands early.
    for mark in ("。", "；", "！", "，"):
        idx = text.find(mark)
        if 0 < idx <= _DEF_MAX_CHARS:
            return text[:idx]
    if len(text) <= _DEF_MAX_CHARS:
        return text
    return text[:_DEF_MAX_CHARS].rstrip("，、 ") + "…"


async def _sources_card(db: AsyncSession) -> dict | None:
    try:
        texts = (await db.execute(select(func.count(BuddhistText.id)))).scalar() or 0
        # DataSource import is local to avoid a heavy import at module load.
        from app.models.source import DataSource

        sources = (
            await db.execute(
                select(func.count(DataSource.id)).where(DataSource.is_active.is_(True))
            )
        ).scalar() or 0
        if not texts and not sources:
            return None
        return {"sources": int(sources), "texts": int(texts)}
    except Exception:
        logger.warning("showcase sources_card failed", exc_info=True)
        return None


async def _chat_card(db: AsyncSession, redis) -> dict | None:
    """A pool of hot questions; the frontend shows one at random per load."""
    try:
        questions = await get_hot_questions(db, redis)
        pool = [q for q in questions if q][:_CHAT_POOL]
        return {"questions": pool} if pool else None
    except Exception:
        logger.warning("showcase chat_card failed", exc_info=True)
        return None


async def _dictionary_card(db: AsyncSession) -> dict | None:
    """A pool of hot terms + short glosses (one batched query over HOT_TERMS)."""
    try:
        rows = (
            await db.execute(
                select(DictionaryEntry.headword, DictionaryEntry.definition)
                .where(DictionaryEntry.headword.in_(HOT_TERMS))
            )
        ).all()
        # One gloss per headword (first row wins), preserving HOT_TERMS order.
        by_term: dict[str, str | None] = {}
        for headword, definition in rows:
            if headword not in by_term:
                by_term[headword] = _short_gloss(definition)
        terms = [{"term": t, "definition": by_term[t]} for t in HOT_TERMS if t in by_term]
        return {"terms": terms} if terms else None
    except Exception:
        logger.warning("showcase dictionary_card failed", exc_info=True)
        return None


async def _kg_card(db: AsyncSession) -> dict | None:
    """A pool of readable knowledge-graph triples (subject —predicate→ object).

    Person-subject filter keeps the sample human-readable (玄奘 —译→ …) without
    an expensive scan; the frontend shows one triple at random per load."""
    try:
        subj = aliased(KGEntity)
        obj = aliased(KGEntity)
        rows = (
            await db.execute(
                select(subj.name_zh, KGRelation.predicate, obj.name_zh)
                .join(subj, KGRelation.subject_id == subj.id)
                .join(obj, KGRelation.object_id == obj.id)
                .where(
                    subj.entity_type == "person",
                    subj.name_zh.is_not(None),
                    obj.name_zh.is_not(None),
                )
                .limit(_POOL)
            )
        ).all()
        triples = [
            {
                "subject": r[0],
                "predicate": _PREDICATE_LABELS.get(r[1], r[1]),
                "object": r[2],
            }
            for r in rows
        ]
        return {"triples": triples} if triples else None
    except Exception:
        logger.warning("showcase kg_card failed", exc_info=True)
        return None


async def _geo_card(db: AsyncSession) -> dict | None:
    """Site count + a pool of place names; the frontend samples a few per load."""
    try:
        count = (
            await db.execute(
                select(func.count(KGEntity.id)).where(KGEntity.entity_type.in_(_GEO_TYPES))
            )
        ).scalar() or 0
        names = (
            await db.execute(
                select(KGEntity.name_zh)
                .where(KGEntity.entity_type.in_(_GEO_TYPES), KGEntity.name_zh.is_not(None))
                .limit(_GEO_POOL)
            )
        ).scalars().all()
        if not count and not names:
            return None
        return {"count": int(count), "places": list(names)}
    except Exception:
        logger.warning("showcase geo_card failed", exc_info=True)
        return None


async def get_home_showcase(db: AsyncSession, redis=None) -> dict:
    """Aggregate the live subtitle content for the homepage hero cards.

    Redis-cached for SHOWCASE_TTL. Each card is best-effort and independently
    nullable — a null card tells the frontend to show its static fallback."""
    if redis is not None:
        try:
            import json

            cached = await redis.get(_SHOWCASE_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.debug("showcase cache read failed", exc_info=True)

    showcase = {
        "sources": await _sources_card(db),
        "chat": await _chat_card(db, redis),
        "dictionary": await _dictionary_card(db),
        "kg": await _kg_card(db),
        "geo": await _geo_card(db),
    }

    if redis is not None:
        try:
            import json

            await redis.set(_SHOWCASE_CACHE_KEY, json.dumps(showcase), ex=SHOWCASE_TTL)
        except Exception:
            logger.debug("showcase cache write failed", exc_info=True)

    return showcase
