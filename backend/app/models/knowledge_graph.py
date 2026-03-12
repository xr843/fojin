from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KGEntity(Base):
    __tablename__ = "kg_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    name_sa: Mapped[str | None] = mapped_column(String(500))
    name_pi: Mapped[str | None] = mapped_column(String(500))
    name_bo: Mapped[str | None] = mapped_column(String(500))
    name_en: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    properties: Mapped[dict | None] = mapped_column(JSON)
    text_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    external_ids: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relations where this entity is the subject
    outgoing_relations: Mapped[list["KGRelation"]] = relationship(
        foreign_keys="KGRelation.subject_id", back_populates="subject"
    )
    incoming_relations: Mapped[list["KGRelation"]] = relationship(
        foreign_keys="KGRelation.object_id", back_populates="object"
    )


class KGRelation(Base):
    __tablename__ = "kg_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("kg_entities.id"), index=True)
    predicate: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    object_id: Mapped[int] = mapped_column(Integer, ForeignKey("kg_entities.id"), index=True)
    properties: Mapped[dict | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Float, server_default="1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    subject: Mapped["KGEntity"] = relationship(foreign_keys=[subject_id], back_populates="outgoing_relations")
    object: Mapped["KGEntity"] = relationship(foreign_keys=[object_id], back_populates="incoming_relations")
