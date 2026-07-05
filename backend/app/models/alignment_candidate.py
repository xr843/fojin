"""Staging table for the cross-canon alignment flywheel.

fojin's moat is verified cross-canon alignment, but it sits at only ~3K
chunk pairs. Growing it safely means a pipeline, not a bulk import: mine
*candidates* automatically (cheap, high-recall, low-precision), then let a
human accept/reject before anything reaches ``alignment_pairs`` (which RAG and
the reader trust as ground truth). This table is the middle stage — candidates
awaiting review — so a bad automatic match never silently becomes a served
"parallel".
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlignmentCandidate(Base):
    __tablename__ = "alignment_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The two aligned chunks, keyed the same way as alignment_pairs so an
    # accepted candidate promotes directly.
    text_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    text_a_juan_num: Mapped[int] = mapped_column(Integer)
    text_a_chunk_index: Mapped[int] = mapped_column(Integer)
    text_a_lang: Mapped[str] = mapped_column(String(10))
    text_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    text_b_juan_num: Mapped[int] = mapped_column(Integer)
    text_b_chunk_index: Mapped[int] = mapped_column(Integer)
    text_b_lang: Mapped[str] = mapped_column(String(10))

    # Cosine similarity from the bootstrap kNN mine (0..1).
    similarity: Mapped[float] = mapped_column(Float)
    # How the candidate was produced (e.g. "knn-bootstrap").
    source: Mapped[str] = mapped_column(String(40), server_default="knn-bootstrap")
    # pending | accepted | rejected
    status: Mapped[str] = mapped_column(String(12), server_default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))

    __table_args__ = (
        # One candidate per directed chunk pair — the miner dedups on this.
        Index(
            "uq_alignment_candidate_pair",
            "text_a_id", "text_a_juan_num", "text_a_chunk_index",
            "text_b_id", "text_b_juan_num", "text_b_chunk_index",
            unique=True,
        ),
    )
