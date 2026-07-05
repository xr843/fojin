"""Staging table for the cross-canon alignment flywheel.

Revision ID: 0167
Revises: 0166
"""

import sqlalchemy as sa
from alembic import op

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alignment_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_a_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("text_a_juan_num", sa.Integer(), nullable=False),
        sa.Column("text_a_chunk_index", sa.Integer(), nullable=False),
        sa.Column("text_a_lang", sa.String(10), nullable=False),
        sa.Column("text_b_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("text_b_juan_num", sa.Integer(), nullable=False),
        sa.Column("text_b_chunk_index", sa.Integer(), nullable=False),
        sa.Column("text_b_lang", sa.String(10), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("source", sa.String(40), server_default="knn-bootstrap", nullable=False),
        sa.Column("status", sa.String(12), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alignment_candidates_text_a_id", "alignment_candidates", ["text_a_id"])
    op.create_index("ix_alignment_candidates_text_b_id", "alignment_candidates", ["text_b_id"])
    op.create_index("ix_alignment_candidates_status", "alignment_candidates", ["status"])
    op.create_index(
        "uq_alignment_candidate_pair",
        "alignment_candidates",
        ["text_a_id", "text_a_juan_num", "text_a_chunk_index",
         "text_b_id", "text_b_juan_num", "text_b_chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_alignment_candidate_pair", table_name="alignment_candidates")
    op.drop_index("ix_alignment_candidates_status", table_name="alignment_candidates")
    op.drop_index("ix_alignment_candidates_text_b_id", table_name="alignment_candidates")
    op.drop_index("ix_alignment_candidates_text_a_id", table_name="alignment_candidates")
    op.drop_table("alignment_candidates")
