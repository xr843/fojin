"""Sentence-level cross-canon alignments (Package C).

A dedicated finer-grained store, deliberately separate from ``alignment_pairs``
(chunk level) so the existing chunk-level consumers — RAG, the unified read
model, the flywheel review — stay untouched. Each row is one aligned sentence
pair produced by subdividing a known chunk-pair's char-offset spans with the
bertalign-core DP in :mod:`app.services.sentence_align`.

Both sides carry the same anchor shape as ``alignment_pairs`` /
``text_apparatus``: (text_id, juan_num, char_start, char_end, lang) where the
offsets index into the (text_id, juan_num, lang) row of ``text_contents.content``
— the re-chunking-stable anchor from migration 0168. ``sent_{a,b}_text`` is the
substring at the row's own offsets, so a row is self-consistent even when the
refinement job fell back to chunk-relative offsets (parent pair not yet
backfilled).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SentenceAlignment(Base):
    __tablename__ = "sentence_alignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Which chunk-level pair this sentence pair refined. The real
    # ON DELETE SET NULL FK to alignment_pairs.id lives in migration 0170 —
    # alignment_pairs has no ORM model (it is accessed via raw SQL), so declaring
    # the FK here would leave Base.metadata unable to resolve it (breaking
    # create_all in tests). Plain column in the ORM, enforced FK in Postgres.
    source_pair_id: Mapped[int | None] = mapped_column(Integer)

    # Side A anchor.
    text_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id", ondelete="CASCADE"))
    text_a_juan_num: Mapped[int] = mapped_column(Integer)
    text_a_char_start: Mapped[int] = mapped_column(Integer)
    text_a_char_end: Mapped[int] = mapped_column(Integer)
    text_a_lang: Mapped[str] = mapped_column(String(10))
    sent_a_text: Mapped[str] = mapped_column(Text)

    # Side B anchor.
    text_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id", ondelete="CASCADE"))
    text_b_juan_num: Mapped[int] = mapped_column(Integer)
    text_b_char_start: Mapped[int] = mapped_column(Integer)
    text_b_char_end: Mapped[int] = mapped_column(Integer)
    text_b_lang: Mapped[str] = mapped_column(String(10))
    sent_b_text: Mapped[str] = mapped_column(Text)

    # Averaged cross-lingual cosine of the aligned sentence(s).
    similarity: Mapped[float] = mapped_column(Float)
    # '1-1' | '1-2' | '2-1' — the bertalign move that produced this pair.
    align_type: Mapped[str] = mapped_column(String(8))
    method: Mapped[str] = mapped_column(String(30), server_default="sentence-bertalign")
    is_verified: Mapped[bool] = mapped_column(Boolean, server_default="false")
    verified_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Idempotent re-runs: one row per (A leading offset, B leading offset).
        UniqueConstraint(
            "text_a_id", "text_a_juan_num", "text_a_char_start",
            "text_b_id", "text_b_juan_num", "text_b_char_start",
            name="uq_sentence_align",
        ),
        Index("ix_sentence_align_a", "text_a_id", "text_a_juan_num"),
        Index("ix_sentence_align_b", "text_b_id", "text_b_juan_num"),
    )
