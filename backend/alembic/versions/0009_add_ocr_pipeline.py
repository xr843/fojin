"""add ocr_tasks, ocr_corrections tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ocr_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=True),
        sa.Column("image_url", sa.String(1000), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("language", sa.String(10), server_default="lzh", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ocr_tasks_user_id", "ocr_tasks", ["user_id"])
    op.create_index("ix_ocr_tasks_status", "ocr_tasks", ["status"])

    op.create_table(
        "ocr_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ocr_task_id", sa.Integer(), sa.ForeignKey("ocr_tasks.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ocr_corrections_ocr_task_id", "ocr_corrections", ["ocr_task_id"])


def downgrade() -> None:
    op.drop_table("ocr_corrections")
    op.drop_table("ocr_tasks")
