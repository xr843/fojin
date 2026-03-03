"""normalize region: 中国→中国大陆, 台湾→中国台湾

Revision ID: 0026
Revises: 0025
Create Date: 2026-03-02
"""

from typing import Sequence, Union
from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    r1 = conn.execute(sa_text("UPDATE data_sources SET region = '中国大陆' WHERE region = '中国'"))
    r2 = conn.execute(sa_text("UPDATE data_sources SET region = '中国台湾' WHERE region = '台湾'"))
    print(f"✅ 中国→中国大陆: {r1.rowcount} rows, 台湾→中国台湾: {r2.rowcount} rows")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa_text("UPDATE data_sources SET region = '中国' WHERE region = '中国大陆'"))
    conn.execute(sa_text("UPDATE data_sources SET region = '台湾' WHERE region = '中国台湾'"))
