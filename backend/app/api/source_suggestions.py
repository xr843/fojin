from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role_guard import require_role
from app.database import get_db
from app.models.source import SourceSuggestion

router = APIRouter(prefix="/source-suggestions", tags=["source-suggestions"])


class SourceSuggestionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(None, max_length=2000)


class SourceSuggestionResponse(BaseModel):
    id: int
    name: str
    url: str
    description: str | None
    status: str
    submitted_at: datetime | None = None

    model_config = {"from_attributes": True}


class SourceSuggestionListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[SourceSuggestionResponse]


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(accepted|rejected|pending)$")


@router.post("", response_model=SourceSuggestionResponse, status_code=201)
async def create_source_suggestion(
    payload: SourceSuggestionCreate,
    db: AsyncSession = Depends(get_db),
):
    suggestion = SourceSuggestion(
        name=payload.name,
        url=payload.url,
        description=payload.description,
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


# --- Admin endpoints ---


@router.get("/pending-count")
async def get_pending_count(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count()).select_from(SourceSuggestion).where(
            SourceSuggestion.status == "pending"
        )
    )
    return {"count": result.scalar_one()}


@router.get("", response_model=SourceSuggestionListResponse)
async def list_source_suggestions(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    query = select(SourceSuggestion)
    count_query = select(func.count()).select_from(SourceSuggestion)
    if status:
        query = query.where(SourceSuggestion.status == status)
        count_query = count_query.where(SourceSuggestion.status == status)
    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(SourceSuggestion.submitted_at.desc())
    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    items = result.scalars().all()
    return {"total": total, "page": page, "size": size, "items": items}


@router.patch("/{suggestion_id}", response_model=SourceSuggestionResponse)
async def update_suggestion_status(
    suggestion_id: int,
    payload: StatusUpdate,
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceSuggestion).where(SourceSuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    suggestion.status = payload.status
    await db.commit()
    await db.refresh(suggestion)
    return suggestion
