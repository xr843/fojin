"""add access_type to data_sources and backfill

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sources that have local data imported
LOCAL_SOURCES = {"cbeta", "suttacentral", "vri", "84000", "sat", "ddb"}


def upgrade() -> None:
    # access_type: local = 本地全量, external = 外链跳转, api = 实时代理
    op.add_column(
        "data_sources",
        sa.Column("access_type", sa.String(20), server_default="external", nullable=False),
    )
    # region column for filtering
    op.add_column(
        "data_sources",
        sa.Column("region", sa.String(50), nullable=True),
    )

    # Backfill: mark sources with actual data as 'local'
    from sqlalchemy import text as sa_text
    conn = op.get_bind()
    for code in LOCAL_SOURCES:
        conn.execute(
            sa_text("UPDATE data_sources SET access_type = 'local' WHERE code = :code"),
            {"code": code},
        )

    # Backfill region from description
    conn.execute(
        sa_text("""
            UPDATE data_sources
            SET region = substring(description from '^(.+?)地区')
            WHERE description LIKE '%地区%' AND region IS NULL
        """)
    )


def downgrade() -> None:
    op.drop_column("data_sources", "region")
    op.drop_column("data_sources", "access_type")
