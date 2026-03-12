from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IIIFManifest(Base):
    __tablename__ = "iiif_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), index=True)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    manifest_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    manifest_json: Mapped[dict | None] = mapped_column(JSON)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    rights: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    text: Mapped["BuddhistText"] = relationship()  # noqa: F821
    source: Mapped["DataSource"] = relationship()  # noqa: F821
