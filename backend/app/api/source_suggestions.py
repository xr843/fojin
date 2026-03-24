from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user
from app.core.exceptions import SuggestionNotFoundError
from app.core.role_guard import require_role
from app.database import get_db
from app.models.notification import Notification
from app.models.source import DataSource, SourceSuggestion
from app.models.user import User

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
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    suggestion = SourceSuggestion(
        name=payload.name,
        url=payload.url,
        description=payload.description,
        user_id=user.id if user else None,
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


@router.delete("/{suggestion_id}", status_code=204)
async def delete_source_suggestion(
    suggestion_id: int,
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SourceSuggestion).where(SourceSuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise SuggestionNotFoundError()
    await db.delete(suggestion)
    await db.commit()


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
        raise SuggestionNotFoundError()

    old_status = suggestion.status
    suggestion.status = payload.status

    # Auto-create DataSource when accepted
    if payload.status == "accepted" and old_status != "accepted":
        await _create_data_source(db, suggestion)

    # Notify the submitting user if they exist
    if suggestion.user_id and payload.status in ("accepted", "rejected"):
        status_label = "已采纳" if payload.status == "accepted" else "已拒绝"
        notification = Notification(
            user_id=suggestion.user_id,
            type="suggestion_review",
            title=f"数据源推荐{status_label}",
            content=f"您推荐的数据源「{suggestion.name}」{status_label}。",
        )
        db.add(notification)

    await db.commit()
    await db.refresh(suggestion)
    return suggestion


async def _create_data_source(db: AsyncSession, suggestion: SourceSuggestion) -> None:
    """Create a DataSource record from an accepted suggestion."""
    # Generate code from URL domain
    parsed = urlparse(suggestion.url)
    domain = parsed.hostname or "unknown"
    # Remove common prefixes
    code = domain.removeprefix("www.").split(".")[0]

    # Check if code already exists, append number if needed
    base_code = code
    counter = 1
    while True:
        existing = await db.execute(
            select(func.count()).select_from(DataSource).where(DataSource.code == code)
        )
        if existing.scalar_one() == 0:
            break
        code = f"{base_code}-{counter}"
        counter += 1

    data_source = DataSource(
        code=code,
        name_zh=suggestion.name,
        base_url=suggestion.url,
        description=suggestion.description,
        access_type="external",
        is_active=True,
    )
    db.add(data_source)
