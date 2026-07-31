from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TextEmbedding(Base):
    __tablename__ = "text_embeddings"
    # Mirrors migration 0168: chunk identity is positional (all alignment
    # stores reference chunks by this triple with no FK), so it must be unique.
    __table_args__ = (
        UniqueConstraint("text_id", "juan_num", "chunk_index", name="uq_text_embeddings_pos"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    juan_num: Mapped[int] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    # embedding column is vector(1536), managed via raw SQL; not mapped here
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Sorts ahead of everything else in the sidebar (migration 0174).
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false(), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatAnswerDiagnostic(Base):
    __tablename__ = "chat_answer_diagnostics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The unique constraint and secondary indexes are owned by migration 0165.
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    trust_state: Mapped[str] = mapped_column(String(30))
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    citation_mutation_count: Mapped[int] = mapped_column(Integer, default=0)
    quote_mutation_count: Mapped[int] = mapped_column(Integer, default=0)
    # How many 「…」 quotes were verbatim-checked. Nullable: rows written before
    # migration 0171 have no value (the count wasn't persisted then).
    quote_checked_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_mutations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    quote_mutations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatAttachment(Base):
    """Uploaded file attached to a chat turn.

    Files are parsed to plain text on upload (see
    ``app.services.attachment_parser``). The frontend gets back an id and
    passes it in ``ChatRequest.attachment_ids``; the chat service then
    prepends the parsed text to the user message before calling the LLM.

    Ownership: ``user_id`` is NULL for anonymous uploads. The chat service
    enforces "user can only consume their own + anonymous rows" so one
    logged-in user can't reference another user's attachment by guessing
    the id.
    """

    __tablename__ = "chat_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The ix_chat_attachments_user_id and ix_chat_attachments_created_at
    # indexes are owned by the alembic migration (0129) — do not set
    # index=True here, otherwise SQLAlchemy create_all would try to make
    # a duplicate.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500))
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SharedQA(Base):
    __tablename__ = "shared_qa"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    creator_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    view_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
