"""Feed service for source updates and academic publication tracking."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import AcademicFeed, SourceUpdate
from app.models.source import DataSource

logger = logging.getLogger(__name__)

FEED_CACHE_TTL = 300  # 5 minutes
SUMMARY_CACHE_TTL = 600  # 10 minutes


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


async def _cache_set(redis, key: str, value: dict, ttl: int = FEED_CACHE_TTL) -> None:
    """Safely cache a serialized value."""
    if redis is None:
        return
    try:
        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        logger.debug("Cache set error for key=%s", key)


def _source_updates_cache_key(source_id, update_type, days, page, page_size) -> str:
    raw = f"{source_id}|{update_type}|{days}|{page}|{page_size}"
    h = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"feed:source_updates:{h}"


def _academic_cache_key(feed_source, category, days, page, page_size) -> str:
    raw = f"{feed_source}|{category}|{days}|{page}|{page_size}"
    h = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"feed:academic:{h}"


async def get_source_updates(
    db: AsyncSession,
    redis=None,
    source_id: int | None = None,
    update_type: str | None = None,
    days: int = 30,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Get recent source updates with optional filtering and pagination."""
    cache_key = _source_updates_cache_key(source_id, update_type, days, page, page_size)
    cached = await _cache_get(redis, cache_key)
    if cached is not None:
        return cached

    cutoff = datetime.now(UTC) - timedelta(days=days)

    q = (
        select(
            SourceUpdate.id,
            SourceUpdate.source_id,
            DataSource.code.label("source_code"),
            DataSource.name_zh.label("source_name_zh"),
            SourceUpdate.update_type,
            SourceUpdate.count,
            SourceUpdate.summary,
            SourceUpdate.detected_at,
        )
        .join(DataSource, SourceUpdate.source_id == DataSource.id)
        .where(SourceUpdate.detected_at >= cutoff)
    )

    if source_id is not None:
        q = q.where(SourceUpdate.source_id == source_id)
    if update_type is not None:
        q = q.where(SourceUpdate.update_type == update_type)

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated results
    q = q.order_by(SourceUpdate.detected_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).all()

    items = [
        {
            "id": r[0],
            "source_id": r[1],
            "source_code": r[2],
            "source_name_zh": r[3],
            "update_type": r[4],
            "count": r[5],
            "summary": r[6],
            "detected_at": r[7],
        }
        for r in rows
    ]

    result = {"items": items, "total": total, "page": page, "page_size": page_size}
    await _cache_set(redis, cache_key, result)
    return result


async def get_academic_feeds(
    db: AsyncSession,
    redis=None,
    feed_source: str | None = None,
    category: str | None = None,
    days: int = 90,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Get recent academic feed entries with optional filtering and pagination."""
    cache_key = _academic_cache_key(feed_source, category, days, page, page_size)
    cached = await _cache_get(redis, cache_key)
    if cached is not None:
        return cached

    cutoff = datetime.now(UTC) - timedelta(days=days)

    q = select(AcademicFeed).where(
        or_(AcademicFeed.published_at >= cutoff, AcademicFeed.published_at.is_(None))
    )

    if feed_source is not None:
        q = q.where(AcademicFeed.feed_source == feed_source)
    if category is not None:
        q = q.where(AcademicFeed.category == category)

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated results
    q = q.order_by(AcademicFeed.published_at.desc().nullslast())
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    items = [
        {
            "id": r.id,
            "feed_source": r.feed_source,
            "title": r.title,
            "url": r.url,
            "summary": r.summary,
            "author": r.author,
            "category": r.category,
            "language": r.language,
            "published_at": r.published_at,
        }
        for r in rows
    ]

    result = {"items": items, "total": total, "page": page, "page_size": page_size}
    await _cache_set(redis, cache_key, result)
    return result


async def get_activity_summary(db: AsyncSession, redis=None) -> dict:
    """Get a combined activity summary for the feed dashboard."""
    cache_key = "feed:summary"
    cached = await _cache_get(redis, cache_key)
    if cached is not None:
        return cached

    cutoff_30d = datetime.now(UTC) - timedelta(days=30)

    # Recent source updates (top 5)
    su_q = (
        select(
            SourceUpdate.id,
            SourceUpdate.source_id,
            DataSource.code.label("source_code"),
            DataSource.name_zh.label("source_name_zh"),
            SourceUpdate.update_type,
            SourceUpdate.count,
            SourceUpdate.summary,
            SourceUpdate.detected_at,
        )
        .join(DataSource, SourceUpdate.source_id == DataSource.id)
        .order_by(SourceUpdate.detected_at.desc())
        .limit(5)
    )
    su_rows = (await db.execute(su_q)).all()
    recent_source_updates = [
        {
            "id": r[0],
            "source_id": r[1],
            "source_code": r[2],
            "source_name_zh": r[3],
            "update_type": r[4],
            "count": r[5],
            "summary": r[6],
            "detected_at": r[7],
        }
        for r in su_rows
    ]

    # Recent academic feeds (top 5)
    af_q = (
        select(AcademicFeed)
        .order_by(AcademicFeed.published_at.desc().nullslast())
        .limit(5)
    )
    af_rows = (await db.execute(af_q)).scalars().all()
    recent_academic = [
        {
            "id": r.id,
            "feed_source": r.feed_source,
            "title": r.title,
            "url": r.url,
            "summary": r.summary,
            "author": r.author,
            "category": r.category,
            "language": r.language,
            "published_at": r.published_at,
        }
        for r in af_rows
    ]

    # Stats
    source_updates_30d = (
        await db.execute(
            select(func.count(SourceUpdate.id)).where(SourceUpdate.detected_at >= cutoff_30d)
        )
    ).scalar() or 0

    academic_feeds_30d = (
        await db.execute(
            select(func.count(AcademicFeed.id)).where(
                or_(AcademicFeed.published_at >= cutoff_30d, AcademicFeed.published_at.is_(None))
            )
        )
    ).scalar() or 0

    active_sources = (
        await db.execute(
            select(func.count(func.distinct(SourceUpdate.source_id))).where(
                SourceUpdate.detected_at >= cutoff_30d
            )
        )
    ).scalar() or 0

    result = {
        "recent_source_updates": recent_source_updates,
        "recent_academic": recent_academic,
        "stats": {
            "source_updates_30d": source_updates_30d,
            "academic_feeds_30d": academic_feeds_30d,
            "active_sources": active_sources,
        },
    }

    await _cache_set(redis, cache_key, result, ttl=SUMMARY_CACHE_TTL)
    return result


async def record_source_update(
    db: AsyncSession,
    source_id: int,
    update_type: str,
    count: int,
    summary: str,
    details: str | None = None,
) -> None:
    """Insert a new SourceUpdate record. Used by import scripts."""
    record = SourceUpdate(
        source_id=source_id,
        update_type=update_type,
        count=count,
        summary=summary,
        details=details,
    )
    db.add(record)
    await db.flush()
