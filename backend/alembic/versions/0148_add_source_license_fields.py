"""add license fields to data_sources

Revision ID: 0148
Revises: 0147
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0148"
down_revision: Union[str, None] = "0147"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LICENSE_COLUMNS = [
    "license_spdx",
    "license_url",
    "license_notes",
    "attribution_required",
    "commercial_allowed",
    "redistribution_allowed",
    "embedding_allowed",
    "license_verified_at",
]


def upgrade() -> None:
    op.add_column("data_sources", sa.Column("license_spdx", sa.String(50), nullable=True))
    op.add_column("data_sources", sa.Column("license_url", sa.String(500), nullable=True))
    op.add_column("data_sources", sa.Column("license_notes", sa.Text(), nullable=True))
    op.add_column("data_sources", sa.Column("attribution_required", sa.Boolean(), nullable=True))
    op.add_column("data_sources", sa.Column("commercial_allowed", sa.Boolean(), nullable=True))
    op.add_column("data_sources", sa.Column("redistribution_allowed", sa.Boolean(), nullable=True))
    op.add_column("data_sources", sa.Column("embedding_allowed", sa.Boolean(), nullable=True))
    op.add_column(
        "data_sources",
        sa.Column("license_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for col in reversed(LICENSE_COLUMNS):
        op.drop_column("data_sources", col)
