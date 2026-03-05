from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText
from app.models.user import ReadingHistory
from app.schemas.bookmark import HistoryResponse


async def get_reading_history(session: AsyncSession, user_id: int, page: int = 1, size: int = 20) -> dict:
    count_result = await session.execute(
        select(func.count()).select_from(ReadingHistory).where(ReadingHistory.user_id == user_id)
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(ReadingHistory, BuddhistText.title_zh, BuddhistText.cbeta_id)
        .join(BuddhistText, ReadingHistory.text_id == BuddhistText.id)
        .where(ReadingHistory.user_id == user_id)
        .order_by(ReadingHistory.last_read_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        HistoryResponse(
            id=rh.id,
            text_id=rh.text_id,
            title_zh=title_zh,
            cbeta_id=cbeta_id,
            juan_num=rh.juan_num,
            last_read_at=rh.last_read_at,
        )
        for rh, title_zh, cbeta_id in result.all()
    ]
    return {"total": total, "page": page, "size": size, "items": items}
