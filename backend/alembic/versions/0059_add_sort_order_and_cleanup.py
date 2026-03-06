"""Add sort_order column, deactivate PKU Buddhism, prioritize CBETA/Dianjin.

Revision ID: 0059
Revises: 0058
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # Add sort_order column (default 0, lower = earlier)
    op.add_column(
        "data_sources",
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    )

    # Initialize sort_order = id for all rows (preserve current ordering)
    op.execute("UPDATE data_sources SET sort_order = id")

    # Prioritize CBETA mirror and Dianjin in 中国大陆 (put them first)
    op.execute("UPDATE data_sources SET sort_order = -2 WHERE code = 'cbeta-cn'")
    op.execute("UPDATE data_sources SET sort_order = -1 WHERE code = 'dianjin'")

    # Deactivate PKU Buddhism (site confirmed down)
    op.execute("UPDATE data_sources SET is_active = false WHERE code = 'pku-buddhism'")


def downgrade() -> None:
    op.execute("UPDATE data_sources SET is_active = true WHERE code = 'pku-buddhism'")
    op.drop_column("data_sources", "sort_order")
