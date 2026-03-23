"""add HNSW vector index on text_embeddings for faster similarity search

Without a vector index, every cosine similarity query performs a full
table scan (O(n)).  An HNSW index reduces this to O(log n) with
sub-millisecond recall at typical dataset sizes.

Revision ID: 0098
Revises: 0097
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0098"
down_revision: Union[str, None] = "0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_text_embeddings_hnsw "
        "ON text_embeddings USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_text_embeddings_hnsw")
