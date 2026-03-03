"""add text_contents table and content fields to buddhist_texts

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add content columns to buddhist_texts
    op.add_column(
        "buddhist_texts",
        sa.Column("has_content", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "buddhist_texts",
        sa.Column("content_char_count", sa.Integer(), server_default="0", nullable=False),
    )

    # Create text_contents table
    op.create_table(
        "text_contents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("text_id", "juan_num", name="uq_text_content_text_juan"),
    )
    op.create_index("ix_text_contents_text_id", "text_contents", ["text_id"])


def downgrade() -> None:
    op.drop_table("text_contents")
    op.drop_column("buddhist_texts", "content_char_count")
    op.drop_column("buddhist_texts", "has_content")
