"""Stats API endpoints for timeline and dashboard."""

from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.stats_service import get_overview, get_timeline

router = APIRouter(prefix="/stats", tags=["stats"])


class TimelineDimension(str, Enum):
    texts = "texts"
    figures = "figures"
    schools = "schools"


@router.get("/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)):
    """Return aggregated platform statistics for the dashboard."""
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return await get_overview(db, redis)


@router.get("/timeline")
async def stats_timeline(
    dimension: TimelineDimension = Query(..., description="Timeline dimension"),
    category: str | None = Query(None, description="Filter by category (comma-separated)"),
    language: str | None = Query(None, description="Filter by language (comma-separated)"),
    source_id: str | None = Query(None, description="Filter by source ID (comma-separated)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(200, ge=1, le=500, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """Return timeline items for visualization."""
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return await get_timeline(db, redis, dimension.value, category, language, source_id, page, page_size)
