"""add text_relations table; add lang to buddhist_texts

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "text_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_a_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("text_b_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("text_a_id", "text_b_id", "relation_type", name="uq_text_relation"),
    )
    op.create_index("ix_text_relations_text_a_id", "text_relations", ["text_a_id"])
    op.create_index("ix_text_relations_text_b_id", "text_relations", ["text_b_id"])

    # Add lang column to buddhist_texts
    op.add_column(
        "buddhist_texts",
        sa.Column("lang", sa.String(10), server_default="lzh", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("buddhist_texts", "lang")
    op.drop_table("text_relations")
