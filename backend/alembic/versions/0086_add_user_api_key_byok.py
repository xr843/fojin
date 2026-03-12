"""Add user API key (BYOK) and daily chat quota fields.

Revision ID: 0086
Revises: 0085
"""

from alembic import op
import sqlalchemy as sa

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("encrypted_api_key", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("api_provider", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("api_model", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("daily_chat_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("last_chat_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_chat_date")
    op.drop_column("users", "daily_chat_count")
    op.drop_column("users", "api_model")
    op.drop_column("users", "api_provider")
    op.drop_column("users", "encrypted_api_key")
