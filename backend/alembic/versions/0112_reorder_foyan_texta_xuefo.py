"""Move foyan, texta-studio, xuefo to higher sort order.

Revision ID: 0112
Revises: 0111
"""

from alembic import op
from sqlalchemy import text

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("UPDATE data_sources SET sort_order = -52 WHERE code = 'foyan'"))
    op.execute(text("UPDATE data_sources SET sort_order = -51 WHERE code = 'texta-studio'"))
    op.execute(text("UPDATE data_sources SET sort_order = -50 WHERE code = 'xuefo'"))


def downgrade() -> None:
    op.execute(text("UPDATE data_sources SET sort_order = 500 WHERE code = 'foyan'"))
    op.execute(text("UPDATE data_sources SET sort_order = 450 WHERE code = 'texta-studio'"))
    op.execute(text("UPDATE data_sources SET sort_order = 0 WHERE code = 'xuefo'"))
