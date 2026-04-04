"""Feed API endpoints for source updates and academic publications."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.feed_service import get_academic_feeds, get_activity_summary, get_source_updates

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("/source-updates")
async def feed_source_updates(
    source_id: int | None = Query(None, description="Filter by data source ID"),
    update_type: str | None = Query(None, description="Filter by update type"),
    days: int = Query(30, ge=1, le=365, description="Look back N days"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Return recent data source sync updates."""
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return await get_source_updates(db, redis, source_id, update_type, days, page, page_size)


@router.get("/academic")
async def feed_academic(
    feed_source: str | None = Query(None, description="Filter by feed source"),
    category: str | None = Query(None, description="Filter by category"),
    days: int = Query(90, ge=1, le=365, description="Look back N days"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Return recent academic feed entries."""
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return await get_academic_feeds(db, redis, feed_source, category, days, page, page_size)


@router.get("/summary")
async def feed_summary(db: AsyncSession = Depends(get_db)):
    """Return combined activity summary with recent updates and stats."""
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return await get_activity_summary(db, redis)
