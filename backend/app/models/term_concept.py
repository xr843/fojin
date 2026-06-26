from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TermConcept(Base):
    """A cross-lingual Buddhist term concept.

    Keyed by a normalized Sanskrit-IAST string (``key``); the per-language
    representative forms are denormalized onto the row so the concept card
    renders without a join. Populated offline by
    ``scripts/build_term_concepts.py`` from structured concordance dictionaries
    (Mahāvyutpatti / 四譯合璧) plus romanized-headword joins.
    """

    __tablename__ = "term_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    sanskrit: Mapped[str | None] = mapped_column(String(200))
    devanagari: Mapped[str | None] = mapped_column(String(200))
    pali: Mapped[str | None] = mapped_column(String(200))
    tibetan: Mapped[str | None] = mapped_column(String(300))
    chinese: Mapped[str | None] = mapped_column(String(200), index=True)
    english: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TermConceptEntry(Base):
    """Link between a :class:`TermConcept` and a ``dictionary_entries`` row.

    ``method`` records which builder rule created the link (``mvp`` /
    ``siyi_tag`` / ``romanized_join``) and ``confidence`` (``high`` / ``medium``)
    so a later phase can audit or roll back specific link classes.
    """

    __tablename__ = "term_concept_entries"
    __table_args__ = (
        UniqueConstraint("concept_id", "dict_entry_id", name="uq_term_concept_entry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("term_concepts.id", ondelete="CASCADE"), index=True
    )
    dict_entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dictionary_entries.id", ondelete="CASCADE"), index=True
    )
    lang: Mapped[str] = mapped_column(String(10), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, server_default="high")
