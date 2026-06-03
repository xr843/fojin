"""add ai_diff_cache table for cross-canon AI difference analysis

Revision ID: 0147
Revises: 0146
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0147"
down_revision: Union[str, None] = "0146"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_diff_cache",
        sa.Column("chunks_hash", sa.String(64), primary_key=True),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ai_diff_cache_created_at",
        "ai_diff_cache",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_diff_cache_created_at", "ai_diff_cache")
    op.drop_table("ai_diff_cache")
