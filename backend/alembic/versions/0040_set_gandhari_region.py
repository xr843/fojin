"""set gandhari source region to 印度

犍陀罗语是古代印度西北地区语言，将该数据源归入"印度"地区。

Revision ID: 0040
Revises: 0039
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE data_sources SET region = '印度' WHERE code = 'gandhari'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE data_sources SET region = NULL WHERE code = 'gandhari'"
    )
