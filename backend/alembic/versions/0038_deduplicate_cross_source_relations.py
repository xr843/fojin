"""deduplicate cross-source kg_relations

For each (subject_id, predicate, object_id) group with multiple rows,
keep the one from auto:cbeta_metadata (preferred) or the lowest id,
and delete the rest.  Expected to remove ~136 duplicate rows.

Also adds a unique index on (subject_id, predicate, object_id) to prevent
future duplicates regardless of source.

Revision ID: 0038
Revises: 0037
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete duplicate rows, keeping the preferred source per group
    op.execute("""
        DELETE FROM kg_relations WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY subject_id, predicate, object_id
                    ORDER BY CASE source WHEN 'auto:cbeta_metadata' THEN 0 ELSE 1 END, id
                ) AS rn
                FROM kg_relations
            ) t WHERE rn > 1
        )
    """)

    # Add a unique index to prevent cross-source duplicates going forward
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_relation_triple
        ON kg_relations (subject_id, predicate, object_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_kg_relation_triple")
