"""按天累加的匿名计数器（daily_metric_counts 的读写）。

游客对话内容刻意不落库（隐私），这里只记"数"。写入用 Postgres UPSERT，
并发下两个游客同秒提问也不会丢数或撞主键。
"""

import logging
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_metric import DailyMetricCount

logger = logging.getLogger(__name__)

ANONYMOUS_MESSAGES = "anonymous_messages"


async def increment_daily_metric(
    db: AsyncSession, metric: str, day: date | None = None, by: int = 1
) -> None:
    """当天 metric 计数 +by（UPSERT，幂等安全）。调用方负责 commit。"""
    stmt = pg_insert(DailyMetricCount).values(
        day=day or date.today(), metric=metric, count=by
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[DailyMetricCount.day, DailyMetricCount.metric],
        set_={"count": DailyMetricCount.count + by},
    )
    await db.execute(stmt)
