"""Add admin_reply and replied_at columns to feedbacks table.

Revision ID: 0105
Revises: 0104
"""

import sqlalchemy as sa
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedbacks", sa.Column("admin_reply", sa.Text(), nullable=True))
    op.add_column("feedbacks", sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("feedbacks", "replied_at")
    op.drop_column("feedbacks", "admin_reply")
