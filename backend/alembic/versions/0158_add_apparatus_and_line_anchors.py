"""add critical apparatus (校勘异文) and line-anchor tables

Revision ID: 0158
Revises: 0157
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0158"
down_revision: str | None = "0157"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "text_apparatus",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("lemma", sa.Text(), nullable=False),
        sa.Column("lemma_siglum", sa.String(length=50), nullable=True),
        sa.Column("app_n", sa.String(length=50), nullable=False),
        sa.Column("aligned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["text_id"], ["buddhist_texts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("text_id", "juan_num", "app_n", name="uq_apparatus_text_juan_app"),
    )
    op.create_index("ix_text_apparatus_text_id", "text_apparatus", ["text_id"])
    op.create_index("ix_text_apparatus_juan_num", "text_apparatus", ["juan_num"])

    op.create_table(
        "apparatus_reading",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("apparatus_id", sa.Integer(), nullable=False),
        sa.Column("reading", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "witnesses",
            sa.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("resp", sa.String(length=100), nullable=True),
        sa.Column("is_omission", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["apparatus_id"], ["text_apparatus.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_apparatus_reading_apparatus_id", "apparatus_reading", ["apparatus_id"])

    op.create_table(
        "text_line_anchors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("char_offset", sa.Integer(), nullable=False),
        sa.Column("line_ref", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["text_id"], ["buddhist_texts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("text_id", "juan_num", "line_ref", name="uq_line_anchor_text_juan_ref"),
    )
    op.create_index("ix_text_line_anchors_text_id", "text_line_anchors", ["text_id"])


def downgrade() -> None:
    op.drop_index("ix_text_line_anchors_text_id", table_name="text_line_anchors")
    op.drop_table("text_line_anchors")
    op.drop_index("ix_apparatus_reading_apparatus_id", table_name="apparatus_reading")
    op.drop_table("apparatus_reading")
    op.drop_index("ix_text_apparatus_juan_num", table_name="text_apparatus")
    op.drop_index("ix_text_apparatus_text_id", table_name="text_apparatus")
    op.drop_table("text_apparatus")
