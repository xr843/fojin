"""Remove 'mul' tag from sources with specific languages listed.

Revision ID: 0108
Revises: 0107
"""

from alembic import op
import sqlalchemy as sa

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 启迪之地: remove mul, keep vi,lzh,pi
    op.execute(
        "UPDATE data_sources SET languages = 'vi,lzh,pi' WHERE code = 'siteofenlightenment'"
    )
    # TITUS: remove mul, add de
    op.execute(
        "UPDATE data_sources SET languages = 'sa,pi,xto,txb,de' WHERE code = 'titus-frankfurt'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE data_sources SET languages = 'vi,lzh,pi,mul' WHERE code = 'siteofenlightenment'"
    )
    op.execute(
        "UPDATE data_sources SET languages = 'sa,pi,xto,txb,mul' WHERE code = 'titus-frankfurt'"
    )
