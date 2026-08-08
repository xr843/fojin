"""按天累加的匿名计数器（首个指标：游客消息数）

Revision ID: 0175
Revises: 0174
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0175"
down_revision: str | None = "0174"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_metric_counts",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "metric"),
    )


def downgrade() -> None:
    op.drop_table("daily_metric_counts")
