"""Add chat_attachments table.

Backs the file-attachment feature for chat. Each row represents a single
uploaded file (PDF / TXT / MD / DOCX / CSV / HTML, ≤10 MB) parsed to
plain text at upload time. The frontend receives the row id and passes
it back in ``ChatRequest.attachment_ids``; the chat service prepends the
parsed text to the user's message before calling the LLM.

Why columns:

- ``user_id`` nullable + ON DELETE SET NULL: anonymous uploads are
  allowed (chat itself supports anon up to FREE_DAILY_LIMIT_ANONYMOUS).
  When a user is deleted we keep the file row for audit/GC but detach
  ownership.
- ``parsed_text`` nullable: parser failures still persist a row so the
  upload endpoint can return 422 with a useful detail message; the
  ``parse_error`` column carries the diagnostic.
- ``consumed_at``: marks when the attachment was first prepended to a
  chat message. NULL = orphan (future cron can GC unconsumed rows older
  than N days).

Indexes mirror the access patterns: by user (admin / future "my files"
view) and by created_at (GC scanning).

Revision ID: 0129
Revises: 0128
"""

import sqlalchemy as sa
from alembic import op

revision = "0129"
down_revision = "0128"


def upgrade() -> None:
    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("parse_error", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_chat_attachments_user_id", "chat_attachments", ["user_id"]
    )
    op.create_index(
        "ix_chat_attachments_created_at", "chat_attachments", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_created_at", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_user_id", table_name="chat_attachments")
    op.drop_table("chat_attachments")
