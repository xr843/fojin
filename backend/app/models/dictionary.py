from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_dict_entry_source_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    headword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    reading: Mapped[str | None] = mapped_column(String(500))
    definition: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), index=True)
    lang: Mapped[str] = mapped_column(String(10), server_default="zh")
    entry_data: Mapped[dict | None] = mapped_column(JSON)
    external_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["DataSource"] = relationship()  # noqa: F821
