"""Models for activity feed: data source updates and academic feeds."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceUpdate(Base):
    """Records changes detected during data source synchronization."""

    __tablename__ = "source_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), index=True)
    update_type: Mapped[str] = mapped_column(String(30), nullable=False)  # new_text/scan/translation/schema/correction
    count: Mapped[int] = mapped_column(Integer, server_default="0")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text)  # JSON string with detailed diff info
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    source: Mapped["DataSource"] = relationship()  # noqa: F821


class AcademicFeed(Base):
    """Academic publications and translation announcements from RSS/API sources."""

    __tablename__ = "academic_feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g. "84000_blog", "jstor", "bdrc_news"
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(50))  # paper/translation/news/digitization/conference
    language: Mapped[str | None] = mapped_column(String(10))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
