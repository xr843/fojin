"""add iiif_manifests table; insert BDRC + IDP data sources

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "iiif_manifests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("manifest_url", sa.String(1000), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=True),
        sa.Column("thumbnail_url", sa.String(1000), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("rights", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_iiif_manifests_text_id", "iiif_manifests", ["text_id"])
    op.create_index("ix_iiif_manifests_source_id", "iiif_manifests", ["source_id"])

    # Insert BDRC data source
    op.execute(
        "INSERT INTO data_sources (code, name_zh, name_en, base_url, api_url, description) "
        "VALUES ('bdrc', '佛教數位資源中心', 'Buddhist Digital Resource Center', "
        "'https://library.bdrc.io', 'https://ldspdi.bdrc.io', "
        "'藏傳佛教文獻數位化計劃')"
    )

    # Insert IDP data source
    op.execute(
        "INSERT INTO data_sources (code, name_zh, name_en, base_url, api_url, description) "
        "VALUES ('idp', '國際敦煌項目', 'International Dunhuang Project', "
        "'https://idp.bl.uk', NULL, "
        "'敦煌文獻數位化')"
    )


def downgrade() -> None:
    op.drop_table("iiif_manifests")
    op.execute("DELETE FROM data_sources WHERE code IN ('bdrc', 'idp')")
