"""widen gaiji.moe_variant_id to accommodate comma-joined IDs

Revision ID: 0151
Revises: 0150
Create Date: 2026-06-10

CBETA encodes multi-MoE-variant references as comma-joined strings,
e.g. "b00914-004_2, a00010-021,b01510-001,a03464-002, c00956-001_1".
Empirically the longest such value is 60 chars (n=31,653 entries
from upstream 4f0a8c31). The original column was sized for a single
ID at varchar(50); widening to varchar(100) gives headroom without
committing to JSON storage.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0151"
down_revision: Union[str, None] = "0150"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "gaiji",
        "moe_variant_id",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "gaiji",
        "moe_variant_id",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
