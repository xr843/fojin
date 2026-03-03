"""deactivate longquan-temple source (site returns 502, all domains down)

Revision ID: 0029
Revises: 0028
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE data_sources SET is_active = false "
        "WHERE code = 'longquan-temple'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE data_sources SET is_active = true "
        "WHERE code = 'longquan-temple'"
    )
