from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText
from app.models.user import Bookmark
from app.schemas.bookmark import BookmarkResponse


async def get_bookmarks(session: AsyncSession, user_id: int, page: int = 1, size: int = 20) -> dict:
    # Count total
    count_result = await session.execute(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user_id)
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(Bookmark, BuddhistText.title_zh, BuddhistText.cbeta_id)
        .join(BuddhistText, Bookmark.text_id == BuddhistText.id)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        BookmarkResponse(
            id=bm.id,
            text_id=bm.text_id,
            title_zh=title_zh,
            cbeta_id=cbeta_id,
            note=bm.note,
            created_at=bm.created_at,
        )
        for bm, title_zh, cbeta_id in result.all()
    ]
    return {"total": total, "page": page, "size": size, "items": items}


async def add_bookmark(
    session: AsyncSession, user_id: int, text_id: int, note: str | None = None
) -> BookmarkResponse:
    # Check text exists
    result = await session.execute(select(BuddhistText).where(BuddhistText.id == text_id))
    bt = result.scalar_one_or_none()
    if bt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="经典未找到")

    # Check duplicate
    result = await session.execute(
        select(Bookmark).where(Bookmark.user_id == user_id, Bookmark.text_id == text_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已收藏")

    bm = Bookmark(user_id=user_id, text_id=text_id, note=note)
    session.add(bm)
    await session.commit()
    await session.refresh(bm)

    return BookmarkResponse(
        id=bm.id,
        text_id=bm.text_id,
        title_zh=bt.title_zh,
        cbeta_id=bt.cbeta_id,
        note=bm.note,
        created_at=bm.created_at,
    )


async def remove_bookmark(session: AsyncSession, user_id: int, text_id: int) -> None:
    result = await session.execute(
        delete(Bookmark).where(Bookmark.user_id == user_id, Bookmark.text_id == text_id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="收藏不存在")
    await session.commit()


async def check_bookmark(session: AsyncSession, user_id: int, text_id: int) -> bool:
    result = await session.execute(
        select(Bookmark.id).where(Bookmark.user_id == user_id, Bookmark.text_id == text_id)
    )
    return result.scalar_one_or_none() is not None
