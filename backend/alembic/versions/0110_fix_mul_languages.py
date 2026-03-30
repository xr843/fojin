"""Remove 'mul' tag from sources with specific languages listed.

Revision ID: 0110
Revises: 0109
"""

from alembic import op

revision = "0110"
down_revision = "0109"
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
