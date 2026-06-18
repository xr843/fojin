from datetime import datetime

from sqlalchemy import ARRAY, JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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


class TextApparatus(Base):
    """A CBETA standoff critical-apparatus (校勘异文) entry: one lemma in the
    base text and the variant readings witnessed by other canons."""

    __tablename__ = "text_apparatus"
    __table_args__ = (
        UniqueConstraint("text_id", "juan_num", "app_n", name="uq_apparatus_text_juan_app"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id", ondelete="CASCADE"), index=True)
    juan_num: Mapped[int | None] = mapped_column(Integer, index=True)
    # Char offsets into TextContent.content. Null when the lemma cannot be
    # located in stored body content (sidelined preface, anchor in a skipped
    # tag, cross-juan span); such rows have aligned=False and are not rendered.
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    lemma: Mapped[str] = mapped_column(Text)
    lemma_siglum: Mapped[str | None] = mapped_column(String(50))
    app_n: Mapped[str] = mapped_column(String(50))
    aligned: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    readings: Mapped[list["ApparatusReading"]] = relationship(
        back_populates="apparatus", cascade="all, delete-orphan"
    )


class ApparatusReading(Base):
    """A single variant reading within an apparatus entry, e.g. 【宋】【元】=辯."""

    __tablename__ = "apparatus_reading"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apparatus_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("text_apparatus.id", ondelete="CASCADE"), index=True
    )
    reading: Mapped[str] = mapped_column(Text, server_default="")
    # Resolved sigla, e.g. ["【宋】", "【元】"]. Native varchar[] on Postgres
    # (prod); JSON under SQLite so the test suite's create_all works (CI builds
    # the full metadata on SQLite). Migration 0158 sets the Postgres default.
    witnesses: Mapped[list[str]] = mapped_column(ARRAY(String).with_variant(JSON, "sqlite"))
    resp: Mapped[str | None] = mapped_column(String(100))
    is_omission: Mapped[bool] = mapped_column(Boolean, server_default="false")

    apparatus: Mapped["TextApparatus"] = relationship(back_populates="readings")


class TextLineAnchor(Base):
    """A CBETA <lb> page-column-line marker, e.g. line_ref "0001a09" at a char
    offset into TextContent.content. Stored for roadmap #2 (URN line-level
    citation + verifiable RAG quotes); no UI yet."""

    __tablename__ = "text_line_anchors"
    __table_args__ = (
        UniqueConstraint("text_id", "juan_num", "line_ref", name="uq_line_anchor_text_juan_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id", ondelete="CASCADE"), index=True)
    juan_num: Mapped[int] = mapped_column(Integer)
    char_offset: Mapped[int] = mapped_column(Integer)
    line_ref: Mapped[str] = mapped_column(String(20))
