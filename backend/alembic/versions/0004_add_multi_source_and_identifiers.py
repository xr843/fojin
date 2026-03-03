"""add data_sources, text_identifiers tables; add source_id to buddhist_texts

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name_zh", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("api_url", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "text_identifiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("source_uid", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "source_uid", name="uq_text_identifier_source_uid"),
    )
    op.create_index("ix_text_identifiers_text_id", "text_identifiers", ["text_id"])
    op.create_index("ix_text_identifiers_source_id", "text_identifiers", ["source_id"])

    # Add source_id to buddhist_texts (nullable for existing rows)
    op.add_column(
        "buddhist_texts",
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id"), nullable=True),
    )

    # Insert CBETA data source
    op.execute(
        "INSERT INTO data_sources (code, name_zh, name_en, base_url, api_url, description) "
        "VALUES ('cbeta', 'CBETA 中華電子佛典協會', 'Chinese Buddhist Electronic Text Association', "
        "'https://cbetaonline.dila.edu.tw', 'https://cbdata.dila.edu.tw/v1.2', "
        "'漢文佛典最大的數位化計劃')"
    )

    # Backfill source_id for existing texts
    op.execute(
        "UPDATE buddhist_texts SET source_id = (SELECT id FROM data_sources WHERE code = 'cbeta')"
    )


def downgrade() -> None:
    op.drop_column("buddhist_texts", "source_id")
    op.drop_table("text_identifiers")
    op.drop_table("data_sources")
