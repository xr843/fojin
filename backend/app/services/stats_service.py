"""Stats aggregation service for dashboard and timeline endpoints."""

import hashlib
import json
import logging

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dynasty_config import resolve_dynasty
from app.models.dictionary import DictionaryEntry
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.source import DataSource
from app.models.text import BuddhistText

logger = logging.getLogger(__name__)

OVERVIEW_CACHE_KEY = "stats:overview"
OVERVIEW_CACHE_TTL = 3600  # 1 hour


async def _cache_get(redis, key: str) -> dict | None:
    """Safely get and deserialize a cached value."""
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        if raw and isinstance(raw, str):
            return json.loads(raw)
    except Exception:
        logger.debug("Cache miss or error for key=%s", key)
    return None


async def _cache_set(redis, key: str, value: dict, ttl: int = OVERVIEW_CACHE_TTL) -> None:
    """Safely cache a serialized value."""
    if redis is None:
        return
    try:
        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        logger.debug("Cache set error for key=%s", key)


async def get_overview(db: AsyncSession, redis=None) -> dict:
    """Return aggregated platform statistics for the dashboard."""
    cached = await _cache_get(redis, OVERVIEW_CACHE_KEY)
    if cached is not None:
        return cached

    # Summary counts
    total_texts = (await db.execute(select(func.count(BuddhistText.id)))).scalar() or 0
    total_sources = (await db.execute(select(func.count(DataSource.id)).where(DataSource.is_active.is_(True)))).scalar() or 0
    total_languages = (await db.execute(select(func.count(func.distinct(BuddhistText.lang))))).scalar() or 0
    total_kg_entities = (await db.execute(select(func.count(KGEntity.id)))).scalar() or 0
    total_kg_relations = (await db.execute(select(func.count(KGRelation.id)))).scalar() or 0
    total_dict_entries = (await db.execute(select(func.count(DictionaryEntry.id)))).scalar() or 0

    summary = {
        "total_texts": total_texts,
        "total_sources": total_sources,
        "total_languages": total_languages,
        "total_kg_entities": total_kg_entities,
        "total_kg_relations": total_kg_relations,
        "total_dict_entries": total_dict_entries,
    }

    # Dynasty distribution
    dynasty_q = (
        select(BuddhistText.dynasty, func.count(BuddhistText.id).label("count"))
        .where(BuddhistText.dynasty.is_not(None))
        .group_by(BuddhistText.dynasty)
        .order_by(func.count(BuddhistText.id).desc())
    )
    dynasty_rows = (await db.execute(dynasty_q)).all()
    dynasty_distribution = []
    for r in dynasty_rows:
        d = resolve_dynasty(r[0])
        dynasty_distribution.append({
            "dynasty": r[0],
            "count": r[1],
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
        })

    # Language distribution
    lang_q = (
        select(BuddhistText.lang, func.count(BuddhistText.id).label("count"))
        .group_by(BuddhistText.lang)
        .order_by(func.count(BuddhistText.id).desc())
    )
    lang_rows = (await db.execute(lang_q)).all()
    language_distribution = [{"language": r[0], "count": r[1]} for r in lang_rows]

    # Category distribution
    cat_q = (
        select(BuddhistText.category, func.count(BuddhistText.id).label("count"))
        .where(BuddhistText.category.is_not(None))
        .group_by(BuddhistText.category)
        .order_by(func.count(BuddhistText.id).desc())
    )
    cat_rows = (await db.execute(cat_q)).all()
    category_distribution = [{"category": r[0], "count": r[1]} for r in cat_rows]

    # Source coverage
    coverage_q = (
        select(
            DataSource.id,
            DataSource.name_zh,
            func.count(BuddhistText.id).label("text_count"),
            func.sum(case((BuddhistText.has_content.is_(True), 1), else_=0)).label("with_content"),
        )
        .join(BuddhistText, BuddhistText.source_id == DataSource.id, isouter=True)
        .where(DataSource.is_active.is_(True))
        .group_by(DataSource.id, DataSource.name_zh)
        .order_by(func.count(BuddhistText.id).desc())
    )
    cov_rows = (await db.execute(coverage_q)).all()
    source_coverage = [
        {
            "source_name": r[1] or f"Source #{r[0]}",
            "full_content": int(r[3] or 0),
            "metadata_only": (r[2] or 0) - int(r[3] or 0),
        }
        for r in cov_rows
    ]

    # Top translators
    trans_q = (
        select(
            BuddhistText.translator,
            func.mode().within_group(BuddhistText.dynasty).label("dynasty"),
            func.count(BuddhistText.id).label("count"),
        )
        .where(BuddhistText.translator.is_not(None))
        .group_by(BuddhistText.translator)
        .order_by(func.count(BuddhistText.id).desc())
        .limit(20)
    )
    trans_rows = (await db.execute(trans_q)).all()
    top_translators = [{"name": r[0], "dynasty": r[1], "count": r[2]} for r in trans_rows]

    result = {
        "summary": summary,
        "dynasty_distribution": dynasty_distribution,
        "language_distribution": language_distribution,
        "category_distribution": category_distribution,
        "source_coverage": source_coverage,
        "top_translators": top_translators,
    }

    await _cache_set(redis, OVERVIEW_CACHE_KEY, result)
    return result


def _timeline_cache_key(dimension: str, category, language, source_id, page: int, page_size: int) -> str:
    """Build a deterministic cache key for timeline queries."""
    raw = f"{dimension}|{category}|{language}|{source_id}|{page}|{page_size}"
    h = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"stats:timeline:{h}"


def _parse_comma_list(value: str | None) -> list[str] | None:
    """Parse a comma-separated string into a list, or None."""
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


async def _timeline_texts(
    db: AsyncSession, category: str | None, language: str | None, source_id: str | None, page: int, page_size: int
) -> dict:
    """Timeline items from BuddhistText."""
    q = select(BuddhistText).where(BuddhistText.dynasty.is_not(None))

    cats = _parse_comma_list(category)
    if cats:
        q = q.where(BuddhistText.category.in_(cats))

    langs = _parse_comma_list(language)
    if langs:
        q = q.where(BuddhistText.lang.in_(langs))

    sids = _parse_comma_list(source_id)
    if sids:
        q = q.where(BuddhistText.source_id.in_([int(s) for s in sids]))

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated results
    q = q.order_by(BuddhistText.id).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = []
    for t in rows:
        d = resolve_dynasty(t.dynasty)
        items.append({
            "id": t.id,
            "name_zh": t.title_zh,
            "name_en": t.title_en,
            "dynasty": t.dynasty,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
            "category": t.category,
            "translator": t.translator,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _timeline_figures(
    db: AsyncSession, _category: str | None, _language: str | None, _source_id: str | None, page: int, page_size: int
) -> dict:
    """Timeline items from KGEntity where entity_type == 'person'."""
    q = select(KGEntity).where(KGEntity.entity_type == "person")

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(KGEntity.id).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = []
    for e in rows:
        dynasty_name = (e.properties or {}).get("dynasty")
        d = resolve_dynasty(dynasty_name)
        items.append({
            "id": e.id,
            "name_zh": e.name_zh,
            "name_en": e.name_en,
            "dynasty": dynasty_name,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def _timeline_schools(
    db: AsyncSession, _category: str | None, _language: str | None, _source_id: str | None, page: int, page_size: int
) -> dict:
    """Timeline items from KGEntity where entity_type == 'school'."""
    q = select(KGEntity).where(KGEntity.entity_type == "school")

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(KGEntity.id).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = []
    for e in rows:
        dynasty_name = (e.properties or {}).get("dynasty")
        d = resolve_dynasty(dynasty_name)
        items.append({
            "id": e.id,
            "name_zh": e.name_zh,
            "name_en": e.name_en,
            "dynasty": dynasty_name,
            "year_start": d["start"] if d else None,
            "year_end": d["end"] if d else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


_DIMENSION_HANDLERS = {
    "texts": _timeline_texts,
    "figures": _timeline_figures,
    "schools": _timeline_schools,
}


async def get_timeline(
    db: AsyncSession,
    redis=None,
    dimension: str = "texts",
    category: str | None = None,
    language: str | None = None,
    source_id: str | None = None,
    page: int = 1,
    page_size: int = 200,
) -> dict:
    """Return paginated timeline items for a given dimension."""
    cache_key = _timeline_cache_key(dimension, category, language, source_id, page, page_size)
    cached = await _cache_get(redis, cache_key)
    if cached is not None:
        return cached

    handler = _DIMENSION_HANDLERS.get(dimension)
    if handler is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    result = await handler(db, category, language, source_id, page, page_size)
    await _cache_set(redis, cache_key, result)
    return result
