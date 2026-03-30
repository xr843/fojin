"""Add embedding column to data_sources for AI Chat source recommendation.

Revision ID: 0108
Revises: 0107
"""

from alembic import op

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE data_sources ADD COLUMN embedding vector(1024)")


def downgrade() -> None:
    op.drop_column("data_sources", "embedding")
