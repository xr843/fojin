"""add dictionary_entries table

Revision ID: 0017
Revises: 0016
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dictionary_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("headword", sa.String(500), nullable=False, index=True),
        sa.Column("reading", sa.String(500), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("data_sources.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("lang", sa.String(10), server_default="zh", nullable=False),
        sa.Column("entry_data", sa.JSON(), nullable=True),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_dict_entry_source_external"),
    )


def downgrade() -> None:
    op.drop_table("dictionary_entries")
