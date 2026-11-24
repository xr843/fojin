from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserExcerpt(Base):
    """读者的个人摘录：阅读页划选一段经文存下（可附一句笔记），只有本人可见。

    与 annotations（公开标注，需审核）分开：2026-11-24 生产里标注总共 4 条，其中
    2 条是读者把经文原句抄进去当摘录、被审核驳回或停在草稿——个人记录不该走审核。

    定位同时存行号与原文：行号（CBETA lb，如 0413a07）重导经文时可能变动，
    前端按「行号附近找原文」重新定位，行号失效时退回全卷找原文。
    """

    __tablename__ = "user_excerpts"
    __table_args__ = (Index("ix_user_excerpts_user_text_juan", "user_id", "text_id", "juan_num"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"))
    juan_num: Mapped[int] = mapped_column(Integer)
    line_ref: Mapped[str | None] = mapped_column(String(16))
    end_line_ref: Mapped[str | None] = mapped_column(String(16))
    quote: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
