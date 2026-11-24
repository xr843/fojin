from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.excerpt import ExcerptCreate, ExcerptListResponse, ExcerptResponse, ExcerptUpdate
from app.services.excerpt import create_excerpt, delete_excerpt, list_excerpts, update_excerpt_note

router = APIRouter(prefix="/excerpts", tags=["excerpts"])


@router.get("", response_model=ExcerptListResponse)
async def get_excerpts(
    text_id: int | None = Query(None),
    juan_num: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的摘录。带 text_id + juan_num 时按经文顺序返回该卷全部（阅读页高亮用）。"""
    return await list_excerpts(db, user.id, text_id=text_id, juan_num=juan_num, page=page, size=size)


@router.post("", response_model=ExcerptResponse)
async def post_excerpt(
    data: ExcerptCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新增摘录（只有本人可见，不需审核）。"""
    return await create_excerpt(db, user.id, data)


@router.patch("/{excerpt_id}", response_model=ExcerptResponse)
async def patch_excerpt(
    excerpt_id: int,
    data: ExcerptUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改摘录的笔记。"""
    return await update_excerpt_note(db, user.id, excerpt_id, data.note)


@router.delete("/{excerpt_id}")
async def remove_excerpt(
    excerpt_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除摘录。"""
    await delete_excerpt(db, user.id, excerpt_id)
    return {"ok": True}
