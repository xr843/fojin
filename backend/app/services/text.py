from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText


async def get_text_by_id(session: AsyncSession, text_id: int) -> BuddhistText | None:
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.id == text_id)
    )
    return result.scalar_one_or_none()


async def get_text_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(BuddhistText.id)))
    return result.scalar() or 0
