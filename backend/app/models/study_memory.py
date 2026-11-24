from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserStudyMemory(Base):
    """读者对「研读记忆」的设置：开关 + 自己写的回答偏好。

    记忆内容本身（最近在读、最近的研读主题、摘录）每次从已有表现算，不在这里存。
    没有这一行 = 开着、没有偏好。
    """

    __tablename__ = "user_study_memory"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
