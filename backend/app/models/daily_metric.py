"""按天累加的匿名计数器。

第一位用户：游客消息数（metric='anonymous_messages'）。游客的对话内容刻意
不落库（隐私 —— 无账号即无删除入口），但管理面板的每日统计只数
chat_messages 就只覆盖注册用户；这张表补上"数"而不碰"内容"。

通用的 (day, metric) 结构是为了下一个同类计数不再走一遍迁移。
"""

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DailyMetricCount(Base):
    __tablename__ = "daily_metric_counts"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
