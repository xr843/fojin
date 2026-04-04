"""Add source_updates and academic_feeds tables for activity feed.

Revision ID: 0116
Revises: 0115
"""

from alembic import op
import sqlalchemy as sa

revision = "0116"
down_revision = "0115"


def upgrade() -> None:
    op.create_table(
        "source_updates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("data_sources.id"), nullable=False, index=True),
        sa.Column("update_type", sa.String(30), nullable=False),
        sa.Column("count", sa.Integer, server_default="0"),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "academic_feeds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("feed_source", sa.String(100), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False, unique=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("academic_feeds")
    op.drop_table("source_updates")
