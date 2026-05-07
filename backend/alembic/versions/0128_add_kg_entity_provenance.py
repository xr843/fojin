"""Add provenance tracking to kg_entities.

Today the only ingestion-lineage signal on a kg_entity row is ``created_at``
(strictly: when the row was first inserted). This is not enough to answer
the operational questions that have already cost real time:

- "T0251 心经 was full of preface text — which other rows are still on the
  pre-fix import and need a re-run?"  Currently: full-table grep.
- "DeepSeek extraction misfired on 2026-04-16; which kg_entities did it
  pollute and how do we roll back?"  Currently: no answer.
- "CBETA / Wikidata published a new dump; how do we re-import only the
  authoritative rows without overwriting the human-curated ones?"
  Currently: full-overwrite or skip.

Three columns close all three gaps:

- ``source_tier``: trust band of the row's ultimate source.
    'authoritative' — DILA / CBETA / canonical catalogs
    'curated'       — Wikipedia / community-edited references
    'derived'       — automated scrapers (Amap, OSM)
    'inferred'      — LLM-assisted extraction (DeepSeek, GPT)

  VARCHAR not ENUM so future tiers can be added without a migration
  (matches the convention set in 0127).

- ``source_version``: a free-form tag identifying the *snapshot* the row
  came from — 'cbeta-2025q1', 'wikidata-dump-20260301',
  'deepseek-chat-2026-04-15'. Lets a sync script select rows older than
  a given snapshot for differential re-import.

- ``ingested_at``: wall-clock time of the most recent ingestion that
  wrote/refreshed this row. Backfilled from ``created_at`` for legacy
  rows so ``ingested_at`` is never NULL after this migration; a row with
  no provenance still has at least an approximate floor.

Composite index on (entity_type, source_tier) supports the common
audit query "show all person rows with tier='inferred'", which is the
shape we'll most often run after a noisy LLM extraction.

Revision ID: 0128
Revises: 0127
"""

import sqlalchemy as sa
from alembic import op

revision = "0128"
down_revision = "0127"


def upgrade() -> None:
    op.add_column(
        "kg_entities",
        sa.Column("source_tier", sa.String(20), nullable=True),
    )
    op.add_column(
        "kg_entities",
        sa.Column("source_version", sa.String(80), nullable=True),
    )
    op.add_column(
        "kg_entities",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill: legacy rows get ingested_at = created_at so the column has
    # a non-NULL floor everywhere. source_tier / source_version stay NULL
    # (= "unknown lineage") until each ingestion script is wired.
    op.execute(
        "UPDATE kg_entities SET ingested_at = created_at WHERE ingested_at IS NULL"
    )

    op.create_index(
        "ix_kg_entities_type_tier",
        "kg_entities",
        ["entity_type", "source_tier"],
    )


def downgrade() -> None:
    op.drop_index("ix_kg_entities_type_tier", table_name="kg_entities")
    op.drop_column("kg_entities", "ingested_at")
    op.drop_column("kg_entities", "source_version")
    op.drop_column("kg_entities", "source_tier")
