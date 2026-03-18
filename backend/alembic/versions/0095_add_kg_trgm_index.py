"""add pg_trgm GIN index on kg_entities.name_zh for fast fuzzy search

Revision ID: 0095
Revises: 0094
Create Date: 2026-03-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0095"
down_revision: str | None = "0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_kg_entities_name_zh_trgm "
        "ON kg_entities USING gin (name_zh gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kg_entities_name_zh_trgm")
