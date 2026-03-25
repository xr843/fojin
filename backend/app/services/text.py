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


async def get_all_text_ids_with_dates(session: AsyncSession) -> list[tuple[int, str]]:
    """Return (id, created_at_date_str) for all texts, ordered by id."""
    result = await session.execute(
        select(BuddhistText.id, BuddhistText.created_at).order_by(BuddhistText.id)
    )
    return [(row[0], row[1].strftime("%Y-%m-%d")) for row in result.all()]
