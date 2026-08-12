"""在线读诵：音频与句级时间戳

Revision ID: 0176
Revises: 0175
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0176"
down_revision: str | None = "0175"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "text_audio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=10), server_default="zh", nullable=False),
        sa.Column("voice_id", sa.String(length=100), nullable=False),
        sa.Column("engine", sa.String(length=40), nullable=False),
        sa.Column("audio_path", sa.String(length=300), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("audio_format", sa.String(length=10), server_default="mp3", nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["text_id"], ["buddhist_texts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "text_id", "juan_num", "lang", "voice_id",
            name="uq_text_audio_text_juan_lang_voice",
        ),
    )
    op.create_index("ix_text_audio_text_id", "text_audio", ["text_id"])

    op.create_table(
        "text_audio_cues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audio_id", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), server_default="prose", nullable=False),
        sa.ForeignKeyConstraint(["audio_id"], ["text_audio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_text_audio_cues_audio_time", "text_audio_cues", ["audio_id", "time_ms"]
    )


def downgrade() -> None:
    op.drop_index("ix_text_audio_cues_audio_time", table_name="text_audio_cues")
    op.drop_table("text_audio_cues")
    op.drop_index("ix_text_audio_text_id", table_name="text_audio")
    op.drop_table("text_audio")
