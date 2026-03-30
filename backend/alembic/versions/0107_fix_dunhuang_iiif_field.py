"""Move dunhuang-iiif from art to dunhuang only.

Revision ID: 0107
Revises: 0106
"""

from alembic import op
import sqlalchemy as sa

revision = "0107"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE data_sources SET research_fields = 'dunhuang' WHERE code = 'dunhuang-iiif'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE data_sources SET research_fields = 'dunhuang,art' WHERE code = 'dunhuang-iiif'"
    )
