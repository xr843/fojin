from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200))
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    access_type: Mapped[str] = mapped_column(String(20), server_default="external")  # local/external/api
    region: Mapped[str | None] = mapped_column(String(50))
    languages: Mapped[str | None] = mapped_column(String(200))  # comma-separated ISO 639 codes
    supports_search: Mapped[bool] = mapped_column(Boolean, server_default="false")
    supports_fulltext: Mapped[bool] = mapped_column(Boolean, server_default="false")
    has_local_fulltext: Mapped[bool] = mapped_column(Boolean, server_default="false")
    has_remote_fulltext: Mapped[bool] = mapped_column(Boolean, server_default="false")
    supports_iiif: Mapped[bool] = mapped_column(Boolean, server_default="false")
    supports_api: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    texts: Mapped[list["BuddhistText"]] = relationship(back_populates="source")  # noqa: F821
    identifiers: Mapped[list["TextIdentifier"]] = relationship(back_populates="source")
    distributions: Mapped[list["SourceDistribution"]] = relationship(  # noqa: F821
        back_populates="source",
        cascade="all, delete-orphan",
    )


class TextIdentifier(Base):
    __tablename__ = "text_identifiers"
    __table_args__ = (
        UniqueConstraint("source_id", "source_uid", name="uq_text_identifier_source_uid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_sources.id"), index=True)
    source_uid: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    text: Mapped["BuddhistText"] = relationship(back_populates="identifiers")  # noqa: F821
    source: Mapped["DataSource"] = relationship(back_populates="identifiers")


class SourceDistribution(Base):
    __tablename__ = "source_distributions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_source_distribution_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str | None] = mapped_column(String(50))
    license_note: Mapped[str | None] = mapped_column(Text)
    is_primary_ingest: Mapped[bool] = mapped_column(Boolean, server_default="false")
    priority: Mapped[int] = mapped_column(Integer, server_default="100")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["DataSource"] = relationship(back_populates="distributions")
