"""add role to users, annotations, annotation_reviews tables

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), server_default="user", nullable=False),
    )

    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("start_pos", sa.Integer(), nullable=False),
        sa.Column("end_pos", sa.Integer(), nullable=False),
        sa.Column("annotation_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="draft",
            nullable=False,
        ),
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
    op.create_index("ix_annotations_text_id", "annotations", ["text_id"])
    op.create_index("ix_annotations_user_id", "annotations", ["user_id"])
    op.create_index("ix_annotations_status", "annotations", ["status"])

    op.create_table(
        "annotation_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("annotation_id", sa.Integer(), sa.ForeignKey("annotations.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_annotation_reviews_annotation_id", "annotation_reviews", ["annotation_id"])


def downgrade() -> None:
    op.drop_table("annotation_reviews")
    op.drop_table("annotations")
    op.drop_column("users", "role")
