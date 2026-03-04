"""fix taipei-npm-guji: catalog.npm.gov.tw → digitalarchive.npm.gov.tw

The old catalog.npm.gov.tw service is completely unreachable.
The collection has moved to digitalarchive.npm.gov.tw (故宮典藏資料檢索).

Revision ID: 0050
Revises: 0049
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE data_sources SET base_url = 'https://digitalarchive.npm.gov.tw/' "
        "WHERE code = 'taipei-npm-guji'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE data_sources SET base_url = 'https://catalog.npm.gov.tw/' "
        "WHERE code = 'taipei-npm-guji'"
    )
