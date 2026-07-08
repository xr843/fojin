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
from itertools import zip_longest

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
_SHOWCASE_CACHE_KEY = "home:showcase:v3"  # v3: sources.names pool added

# A small candidate pool size for rotation-by-seed queries: fetch a bounded set
# cheaply, then pick one deterministically per time bucket.
_POOL = 12

# KG card: query each of these predicates separately and round-robin the results
# so the pool spans relation types instead of whatever the physical scan hits
# first (which was 100% active_in). translated (译) + teacher_of (授学) are the
# illustrative person→X edges; active_in (活跃于) is filler. All three have
# person subjects.
_KG_FEATURED_PREDICATES = ("translated", "teacher_of", "active_in")
_KG_PER_PREDICATE = 5

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
_SOURCES_POOL = 12

# Curated example names for the geo card. The geo layer is a global OSM/Wikidata
# harvest, so most rows' name_zh holds a foreign native name (고경사, "Chùa …",
# even a typo'd "Tibetian Budist Temple"). Sampling arbitrary rows put those on
# the homepage. This card is a storefront: show a fixed pool of well-known
# Chinese temples instead. All entries are monasteries (寺院) so they match the
# card's "座佛教寺院" label — no sacred mountains, which aren't temples. The real
# total comes from the live monastery count; only these names are curated.
_GEO_FEATURED = (
    "少林寺", "灵隐寺", "白马寺", "寒山寺", "法门寺", "大慈恩寺",
    "国清寺", "栖霞寺", "南普陀寺", "金山寺", "大昭寺", "扎什伦布寺",
    "隆兴寺", "广济寺", "华严寺", "归元寺",
)


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
        # A pool of active source names so the card varies per load (the raw
        # counts alone never change — and are already shown in the hero stats).
        names = (
            await db.execute(
                select(DataSource.name_zh)
                .where(DataSource.is_active.is_(True), DataSource.name_zh.is_not(None))
                .limit(_SOURCES_POOL)
            )
        ).scalars().all()
        if not texts and not sources:
            return None
        # texts kept for backward compat (PWA-cached old frontend reads it).
        return {"sources": int(sources), "texts": int(texts), "names": list(names)}
    except Exception:
        logger.warning("showcase sources_card failed", exc_info=True)
        return None


async def _chat_card(db: AsyncSession, redis) -> dict | None:
    """A pool of hot questions; the frontend shows one at random per load."""
    try:
        questions = await get_hot_questions(db, redis)
        pool = [q for q in questions if q][:_CHAT_POOL]
        # `question` (first of pool) is a legacy field kept for one release so a
        # PWA-cached old frontend (which reads .question) still works during the
        # service-worker update window. Safe to drop once SWs have propagated.
        return {"questions": pool, "question": pool[0]} if pool else None
    except Exception:
        logger.warning("showcase chat_card failed", exc_info=True)
        return None


def _has_cjk(s: str | None) -> bool:
    """True if the string contains at least one CJK ideograph — used to tell a
    real Chinese gloss from a bare English/Sanskrit transliteration."""
    return any("一" <= c <= "鿿" for c in (s or ""))


async def _dictionary_card(db: AsyncSession) -> dict | None:
    """A pool of hot terms + short glosses (one batched query over HOT_TERMS)."""
    try:
        rows = (
            await db.execute(
                select(DictionaryEntry.headword, DictionaryEntry.definition)
                .where(DictionaryEntry.headword.in_(HOT_TERMS))
            )
        ).all()
        # Prefer a Chinese gloss per headword. A single-entry term (e.g. 如来 whose
        # only entry defines it as "Tathagata") would otherwise deterministically
        # surface a bare transliteration, which reads as broken on a 佛学辞典 card.
        # Keep the first gloss seen, but upgrade to a Chinese one if a later row
        # has it.
        by_term: dict[str, str | None] = {}
        for headword, definition in rows:
            gloss = _short_gloss(definition)
            if not gloss:
                continue
            cur = by_term.get(headword)
            if cur is None or (not _has_cjk(cur) and _has_cjk(gloss)):
                by_term[headword] = gloss
        # Only surface terms whose chosen gloss is actually Chinese — drop any
        # term left with only a non-Chinese gloss rather than show it.
        terms = [
            {"term": t, "definition": by_term[t]}
            for t in HOT_TERMS
            if by_term.get(t) and _has_cjk(by_term[t])
        ]
        if not terms:
            return None
        # Legacy single-pick fields (see _chat_card) for PWA-cached old frontends.
        return {"terms": terms, "term": terms[0]["term"], "definition": terms[0]["definition"]}
    except Exception:
        logger.warning("showcase dictionary_card failed", exc_info=True)
        return None


async def _kg_card(db: AsyncSession) -> dict | None:
    """A pool of readable knowledge-graph triples (subject —predicate→ object).

    Person-subject filter keeps the sample human-readable (玄奘 —译→ …). We query
    each featured predicate separately and round-robin the results so the pool
    spans relation TYPES: a single ``LIMIT`` over the physical scan returned 100%
    ``active_in→唐`` and hid the 22k teacher_of / 2.8k translated edges. The
    frontend shows one triple at random per load."""
    try:
        subj = aliased(KGEntity)
        obj = aliased(KGEntity)

        async def _pred_rows(pred: str) -> list:
            return (
                await db.execute(
                    select(subj.name_zh, KGRelation.predicate, obj.name_zh)
                    .join(subj, KGRelation.subject_id == subj.id)
                    .join(obj, KGRelation.object_id == obj.id)
                    .where(
                        subj.entity_type == "person",
                        KGRelation.predicate == pred,
                        subj.name_zh.is_not(None),
                        obj.name_zh.is_not(None),
                    )
                    .limit(_KG_PER_PREDICATE)
                )
            ).all()

        # translated (译) + teacher_of (授学) are the illustrative ones; active_in
        # (活跃于) is kept as filler but no longer allowed to dominate.
        per_pred = [await _pred_rows(p) for p in _KG_FEATURED_PREDICATES]
        rows = [r for tier in zip_longest(*per_pred) for r in tier if r]
        triples = [
            {
                "subject": r[0],
                "predicate": _PREDICATE_LABELS.get(r[1], r[1]),
                "object": r[2],
            }
            for r in rows
        ]
        if not triples:
            return None
        # Legacy single-pick fields (see _chat_card) for PWA-cached old frontends.
        return {"triples": triples, **triples[0]}
    except Exception:
        logger.warning("showcase kg_card failed", exc_info=True)
        return None


async def _geo_card(db: AsyncSession) -> dict | None:
    """Live site count + a curated pool of well-known temple names.

    The count is the live monastery total — monasteries only, to match the
    "座佛教寺院" label (the ``place`` rows, ~0.6%, aren't temples). The example
    names are the curated ``_GEO_FEATURED`` pool (not sampled from the DB, which
    would surface foreign native names). The frontend samples a few names per
    load. Returns None when there is no geo data so the card degrades cleanly.
    """
    try:
        count = (
            await db.execute(
                select(func.count(KGEntity.id)).where(KGEntity.entity_type == "monastery")
            )
        ).scalar() or 0
        if not count:
            return None
        return {"count": int(count), "places": list(_GEO_FEATURED)}
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
