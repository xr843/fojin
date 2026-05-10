from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText


async def get_text_by_id(session: AsyncSession, text_id: int) -> BuddhistText | None:
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.id == text_id)
    )
    return result.scalar_one_or_none()


async def get_text_id_by_cbeta(session: AsyncSession, cbeta_id: str) -> int | None:
    """Resolve a CBETA ID (e.g. ``T0278``) to the lowest internal text id.

    cbeta_id 在 buddhist_texts 上为 unique，但若未来同一编号跨数据源出现，
    取 id 最小那条以保持可预测的跳转目标。"""
    result = await session.execute(
        select(BuddhistText.id)
        .where(BuddhistText.cbeta_id == cbeta_id)
        .order_by(BuddhistText.id.asc())
        .limit(1)
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
