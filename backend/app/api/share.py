import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_optional_user
from app.database import get_db
from app.models.chat import SharedQA
from app.models.user import User
from app.schemas.chat import (
    ShareQACreateResponse,
    ShareQARequest,
    ShareQAResponse,
)

router = APIRouter(prefix="/share", tags=["share"])


_ID_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_short_id(length: int = 12) -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(length))


def _public_share_url(short_id: str) -> str:
    base = settings.oauth_redirect_base.rstrip("/")
    return f"{base}/share/qa/{short_id}"


@router.post("/qa", response_model=ShareQACreateResponse)
async def create_shared_qa(
    payload: ShareQARequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a publicly shareable Q&A snapshot. Anyone with the short ID can read it.

    创建公开可访问的问答快照,用于社交分享。"""
    sources_payload = (
        [s.model_dump() for s in payload.sources] if payload.sources else None
    )

    for _ in range(5):
        short_id = _generate_short_id()
        existing = await db.scalar(select(SharedQA.id).where(SharedQA.id == short_id))
        if not existing:
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to allocate share id")

    record = SharedQA(
        id=short_id,
        question=payload.question,
        answer=payload.answer,
        sources=sources_payload,
        creator_user_id=user.id if user else None,
    )
    db.add(record)
    await db.commit()

    return ShareQACreateResponse(id=short_id, url=_public_share_url(short_id))


@router.get("/qa/{share_id}", response_model=ShareQAResponse)
async def get_shared_qa(
    share_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Fetch a publicly shared Q&A. Increments view count.

    获取一条公开分享的问答,会递增浏览次数。"""
    record = await db.scalar(select(SharedQA).where(SharedQA.id == share_id))
    if not record:
        raise HTTPException(status_code=404, detail="Shared Q&A not found")

    await db.execute(
        update(SharedQA)
        .where(SharedQA.id == share_id)
        .values(view_count=SharedQA.view_count + 1)
    )
    await db.commit()

    return ShareQAResponse(
        id=record.id,
        question=record.question,
        answer=record.answer,
        sources=record.sources,
        view_count=record.view_count + 1,
        created_at=record.created_at,
    )
