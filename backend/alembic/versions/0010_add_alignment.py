"""add alignment_tasks, alignment_pairs tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alignment_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_a_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("text_b_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("method", sa.String(20), server_default="auto", nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alignment_tasks_status", "alignment_tasks", ["status"])

    op.create_table(
        "alignment_pairs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("alignment_tasks.id"), nullable=False),
        sa.Column("segment_a", sa.Text(), nullable=False),
        sa.Column("segment_b", sa.Text(), nullable=False),
        sa.Column("position_a", sa.Integer(), nullable=False),
        sa.Column("position_b", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alignment_pairs_task_id", "alignment_pairs", ["task_id"])


def downgrade() -> None:
    op.drop_table("alignment_pairs")
    op.drop_table("alignment_tasks")
