"""Homepage dynamic content endpoints."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.home_showcase import SHOWCASE_TTL, get_home_showcase

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/showcase")
async def home_showcase(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Live subtitle content for the 6 hero feature cards.

    Public, Redis-cached, best-effort: each card key may be null, in which case
    the frontend renders that card's static fallback. Served with a matching
    Cache-Control so the CDN/browser also caches it briefly.
    """
    redis = getattr(request.app.state, "redis", None)
    showcase = await get_home_showcase(db, redis)
    response.headers["Cache-Control"] = f"public, max-age={SHOWCASE_TTL}"
    return showcase
