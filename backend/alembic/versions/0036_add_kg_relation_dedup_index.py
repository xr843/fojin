"""add unique index on kg_relations for relation dedup

Partial unique index: (subject_id, predicate, object_id, source)
WHERE source IS NOT NULL. Enforces idempotent auto-extraction
while leaving manually-created (source=NULL) relations unconstrained.

Revision ID: 0036
Revises: 0035
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_kg_relation_dedup
        ON kg_relations (subject_id, predicate, object_id, source)
        WHERE source IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_kg_relation_dedup")
