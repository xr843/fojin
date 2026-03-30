"""Restore 'mul' tag - both sites are genuinely multilingual.

Revision ID: 0111
Revises: 0110
"""

from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 启迪之地: restore mul, add en (has English translations)
    op.execute(
        "UPDATE data_sources SET languages = 'vi,lzh,pi,en,mul' WHERE code = 'siteofenlightenment'"
    )
    # TITUS: restore mul, keep de (German institution)
    op.execute(
        "UPDATE data_sources SET languages = 'sa,pi,xto,txb,de,mul' WHERE code = 'titus-frankfurt'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE data_sources SET languages = 'vi,lzh,pi' WHERE code = 'siteofenlightenment'"
    )
    op.execute(
        "UPDATE data_sources SET languages = 'sa,pi,xto,txb,de' WHERE code = 'titus-frankfurt'"
    )
