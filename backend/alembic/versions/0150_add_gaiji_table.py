"""add gaiji table for CBETA rare-character normalization

Revision ID: 0150
Revises: 0149
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0150"
down_revision: Union[str, None] = "0149"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gaiji",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cb_code", sa.String(length=20), nullable=False),
        sa.Column("composition", sa.String(length=200), nullable=True),
        sa.Column("unicode_char", sa.String(length=8), nullable=True),
        sa.Column("unicode_codepoint", sa.String(length=20), nullable=True),
        sa.Column("norm_unicode_char", sa.String(length=8), nullable=True),
        sa.Column("norm_big5_char", sa.String(length=8), nullable=True),
        sa.Column("pua_codepoint", sa.String(length=20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("moe_variant_id", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="cbeta"),
        sa.Column("upstream_version", sa.String(length=50), nullable=True),
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
        sa.UniqueConstraint("cb_code", name="uq_gaiji_cb_code"),
    )
    op.create_index("ix_gaiji_cb_code", "gaiji", ["cb_code"])
    op.create_index("ix_gaiji_composition", "gaiji", ["composition"])
    op.create_index("ix_gaiji_norm_unicode_char", "gaiji", ["norm_unicode_char"])


def downgrade() -> None:
    op.drop_index("ix_gaiji_norm_unicode_char", table_name="gaiji")
    op.drop_index("ix_gaiji_composition", table_name="gaiji")
    op.drop_index("ix_gaiji_cb_code", table_name="gaiji")
    op.drop_table("gaiji")
