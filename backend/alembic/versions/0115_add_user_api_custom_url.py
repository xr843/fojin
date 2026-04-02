"""Add api_custom_url column to users table for custom BYOK providers.

Revision ID: 0115
Revises: 0114
"""

from alembic import op
import sqlalchemy as sa

revision = "0115"
down_revision = "0114"


def upgrade() -> None:
    op.add_column("users", sa.Column("api_custom_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "api_custom_url")
