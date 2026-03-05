from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BuddhistText(Base):
    __tablename__ = "buddhist_texts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    taisho_id: Mapped[str | None] = mapped_column(String(50), index=True)
    cbeta_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title_zh: Mapped[str] = mapped_column(String(500), index=True)
    title_en: Mapped[str | None] = mapped_column(String(500))
    title_sa: Mapped[str | None] = mapped_column(String(500))
    title_bo: Mapped[str | None] = mapped_column(String(500))
    title_pi: Mapped[str | None] = mapped_column(String(500))
    translator: Mapped[str | None] = mapped_column(String(200))
    dynasty: Mapped[str | None] = mapped_column(String(50))
    fascicle_count: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(100))
    subcategory: Mapped[str | None] = mapped_column(String(200))
    cbeta_url: Mapped[str | None] = mapped_column(String(500))
    has_content: Mapped[bool] = mapped_column(Boolean, server_default="false")
    content_char_count: Mapped[int] = mapped_column(Integer, server_default="0")
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), index=True)
    lang: Mapped[str] = mapped_column(String(10), server_default="lzh")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    contents: Mapped[list["TextContent"]] = relationship(back_populates="text")
    source: Mapped["DataSource"] = relationship(back_populates="texts")  # noqa: F821
    identifiers: Mapped[list["TextIdentifier"]] = relationship(back_populates="text")  # noqa: F821


class TextContent(Base):
    __tablename__ = "text_contents"
    __table_args__ = (
        UniqueConstraint("text_id", "juan_num", "lang", name="uq_text_content_text_juan_lang"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id", ondelete="CASCADE"), index=True)
    juan_num: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_html: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(10), server_default="lzh")
    char_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    text: Mapped["BuddhistText"] = relationship(back_populates="contents")
