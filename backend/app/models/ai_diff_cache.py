from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiDiffCache(Base):
    """Cache of LLM-generated cross-canon difference analyses.

    Keyed by a deterministic hash of (sorted chunk identifiers + prompt_version + model),
    so identical requests reuse the previous analysis verbatim.
    """

    __tablename__ = "ai_diff_cache"

    chunks_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
