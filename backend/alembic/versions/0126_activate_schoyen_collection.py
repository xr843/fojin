"""Activate the pre-existing schoyen-collection row.

When 0125 added 8 new sources, the `schoyen-collection` INSERT was
silently skipped by ON CONFLICT (code) DO NOTHING because a row with
that code had existed since 2026-03-02 with is_active=false. The row
was never surfaced in fojin.app/api/sources, which is why dedup against
the public list missed it.

Flip is_active=true and turn on supports_search so the row joins the
other seven additions from 0125 and the public count goes from 543 → 544.

Revision ID: 0126
Revises: 0125
"""

from alembic import op
from sqlalchemy import text

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "UPDATE data_sources "
            "SET is_active = true, supports_search = true "
            "WHERE code = 'schoyen-collection'"
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "UPDATE data_sources "
            "SET is_active = false, supports_search = false "
            "WHERE code = 'schoyen-collection'"
        )
    )
