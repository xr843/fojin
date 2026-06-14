"""add GIN trigram index on text_contents.content for ILIKE content search

Revision ID: 0157
Revises: 0156
Create Date: 2026-06-14

api/seo_dict.py._fetch_reverse_index (and other content-substring lookups) run
`text_contents.content ILIKE '%term%'`. The code comment claimed the column was
trigram-indexed, but NO such index existed in production — so every call
seq-scanned the 406MB text_contents table. Under crawler load on /seo dict
pages these queries (60s+ each) piled up and exhausted the Postgres connection
pool (2026-06-14 incident). A GIN trigram index makes substring ILIKE
sub-second, matching the existing pattern in 0039 (kg_entities.name_zh).

The index was built manually on prod ahead of this migration; CREATE INDEX
IF NOT EXISTS keeps it a no-op there and reproducible on fresh deploys.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0157"
down_revision: str | None = "0156"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_text_contents_content_trgm "
        "ON text_contents USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_text_contents_content_trgm")
