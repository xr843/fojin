"""Add feedback column to chat_messages table.

Revision ID: 0103
Revises: 0102
"""

from alembic import op
import sqlalchemy as sa

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("feedback", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "feedback")
