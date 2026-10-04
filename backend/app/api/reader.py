"""阅读器辅助接口：选中一句 → AI 白话释义。"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import get_real_client_ip
from app.core.deps import get_optional_user
from app.database import get_db
from app.models.user import User
from app.services.vernacular import get_vernacular

router = APIRouter(prefix="/reader", tags=["reader"])

# 选文上限与前端 VERNACULAR_MAX_CHARS 保持一致，否则长选区会 422
VERNACULAR_MAX_CHARS = 200
CONTEXT_MAX_CHARS = 200


class VernacularRequest(BaseModel):
    text_id: int = Field(..., ge=1)
    sentence: str = Field(..., min_length=1, max_length=VERNACULAR_MAX_CHARS)
    before: str = Field("", max_length=CONTEXT_MAX_CHARS)
    after: str = Field("", max_length=CONTEXT_MAX_CHARS)


class VernacularResponse(BaseModel):
    translation: str
    uncertain: bool
    model: str
    prompt_version: str
    cached: bool


@router.post("/vernacular", response_model=VernacularResponse)
async def vernacular(
    payload: VernacularRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> VernacularResponse:
    """选文的 AI 白话释义（带标签、仅供参考）。公开接口；缓存未命中时消耗每日额度。"""
    redis = getattr(request.app.state, "redis", None)
    identity = f"user:{user.id}" if user else f"ip:{get_real_client_ip(request, default='unknown')}"
    result = await get_vernacular(
        db,
        text_id=payload.text_id,
        sentence=payload.sentence.strip(),
        before=payload.before,
        after=payload.after,
        redis=redis,
        quota_identity=identity,
        quota_is_authenticated=user is not None,
    )
    return VernacularResponse(**result)
