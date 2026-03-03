"""add pg_trgm extension and GIN index on kg_entities.name_zh

Enables fast trigram-based fuzzy search on entity names.
Falls back gracefully if extension is already installed.

Revision ID: 0039
Revises: 0038
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_kg_entities_name_zh_trgm
        ON kg_entities USING gin (name_zh gin_trgm_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kg_entities_name_zh_trgm")
