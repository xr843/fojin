from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnswerReview(Base):
    """Admin verdict for one assistant chat message in the answer-quality queue.

    The detection layer is computed live from chat_messages; this table is the
    only persisted state. ``detection_reasons`` + ``suspicion_score`` snapshot
    why the message was flagged at review time, so the labeled dataset records
    its own provenance. ``unique(message_id)`` makes review idempotent.
    """

    __tablename__ = "answer_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The fk_answer_reviews_message FK + uq_answer_reviews_message unique
    # constraint are owned by migration 0164 — do not add index=True/unique=True
    # here, or create_all would try to duplicate them.
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(10))  # "good" | "bad"
    failure_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    detection_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suspicion_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
