from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Work(Base):
    """FRBR Work 层：抽象作品，聚合跨语言 / 跨藏的多个见证本 (BuddhistText)。

    纯增量叠加，不改动 BuddhistText / text_identifiers / alignment_pairs。
    身份复用既有权威号：sc_root_uid (SuttaCentral) / toh_number (84000) /
    title_sa (Skt 题名，跨柱主桥梁)。
    """

    __tablename__ = "works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title_primary: Mapped[str] = mapped_column(String(500), index=True)
    title_sa: Mapped[str | None] = mapped_column(String(500), index=True)
    title_pi: Mapped[str | None] = mapped_column(String(500))
    sc_root_uid: Mapped[str | None] = mapped_column(String(200), index=True)
    toh_number: Mapped[str | None] = mapped_column(String(50), index=True)
    category: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    witnesses: Mapped[list["WorkWitness"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )
    aliases: Mapped[list["WorkAlias"]] = relationship(
        back_populates="work", cascade="all, delete-orphan"
    )


class WorkWitness(Base):
    """Work ↔ 见证本 (BuddhistText) 映射。一个见证本通常只属一个 Work。"""

    __tablename__ = "work_witnesses"
    __table_args__ = (
        UniqueConstraint("work_id", "text_id", name="uq_work_witness_work_text"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("works.id", ondelete="CASCADE"), index=True
    )
    text_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("buddhist_texts.id", ondelete="CASCADE"), index=True
    )
    # root | translation | commentary | edition | fragment
    role: Mapped[str] = mapped_column(String(20), server_default="translation")
    lang: Mapped[str] = mapped_column(String(10))
    # taisho | xuzang | pali | kangyur | gretil | ...
    canon: Mapped[str | None] = mapped_column(String(50))
    # verified | auto | tentative
    confidence: Mapped[str] = mapped_column(String(20), server_default="auto")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    work: Mapped["Work"] = relationship(back_populates="witnesses")


class WorkAlias(Base):
    """Work 的备用作品号 / 异名（scheme: sc_uid|toh|taisho|skt_title|...）。"""

    __tablename__ = "work_aliases"
    __table_args__ = (
        UniqueConstraint("scheme", "value", name="uq_work_alias_scheme_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("works.id", ondelete="CASCADE"), index=True
    )
    scheme: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    work: Mapped["Work"] = relationship(back_populates="aliases")
