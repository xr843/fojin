from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    password_version: Mapped[int] = mapped_column(Integer, server_default="0")
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # BYOK (Bring Your Own Key)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Version of the KDF that produced encrypted_api_key. 1 = legacy
    # (SHA-256 of JWT_SECRET_KEY), 2 = standalone API_KEY_ENCRYPTION_KEY.
    # See app/core/crypto.py and migration 0130.
    api_key_kdf_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    api_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    api_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    api_custom_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    daily_chat_count: Mapped[int] = mapped_column(Integer, server_default="0")
    last_chat_date = mapped_column(Date, nullable=True)


class SocialAccount(Base):
    """Third-party OAuth accounts linked to a user."""

    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_social_provider_uid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))  # github, google, phone
    provider_user_id: Mapped[str] = mapped_column(String(200))  # GitHub uid / Google sub / phone number
    provider_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON extra info
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (UniqueConstraint("user_id", "text_id", name="uq_bookmark_user_text"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReadingHistory(Base):
    __tablename__ = "reading_history"
    __table_args__ = (UniqueConstraint("user_id", "text_id", name="uq_reading_history_user_text"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    text_id: Mapped[int] = mapped_column(Integer, ForeignKey("buddhist_texts.id"), index=True)
    juan_num: Mapped[int] = mapped_column(Integer, server_default="1")
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordChangeAudit(Base):
    """One row per password-change attempt — success or failure.

    Source of truth for "who changed user X's password and from where".
    No FK to ``users``: audit rows must outlive user deletion. Index is
    on ``(user_id, changed_at DESC)`` for the common "show recent
    activity for this user" query.
    """

    __tablename__ = "password_change_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # 'success' | 'wrong_old_password' | 'same_as_old' (VARCHAR for
    # extensibility — see migration 0127).
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    via: Mapped[str] = mapped_column(String(20), nullable=False, server_default="self")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
