from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.bookmark import BookmarkCreate, BookmarkResponse
from app.services.bookmark import add_bookmark, check_bookmark, get_bookmarks, remove_bookmark

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.get("")
async def list_bookmarks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的收藏列表。"""
    return await get_bookmarks(db, user.id, page, size)


@router.post("", response_model=BookmarkResponse)
async def create_bookmark(
    data: BookmarkCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """收藏经典。"""
    return await add_bookmark(db, user.id, data.text_id, data.note)


@router.delete("/{text_id}")
async def delete_bookmark(
    text_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消收藏。"""
    await remove_bookmark(db, user.id, text_id)
    return {"ok": True}


@router.get("/check/{text_id}")
async def is_bookmarked(
    text_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """检查是否已收藏。"""
    bookmarked = await check_bookmark(db, user.id, text_id)
    return {"bookmarked": bookmarked}
