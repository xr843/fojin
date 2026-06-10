"""activate suttacentral-voice source row

Revision ID: 0153
Revises: 0152
Create Date: 2026-06-10

E2E verification (2026-06-10) discovered the row had been present in
data_sources since before Wave 1.2 (id=213) but with is_active=False,
which means /api/sources filtered it out. Wave 1.2b's 0149 license
backfill nonetheless matched the row by code and populated CC0-1.0 +
embedding_allowed=true, so the data is already correct — only the
visibility flag is wrong.

The 0152 migration I shipped earlier inserted a fresh row with
ON CONFLICT (code) DO NOTHING, which silently did nothing because the
row was already there. This migration finishes the job by flipping
is_active=true so the existing well-formed row reaches the API.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0153"
down_revision: Union[str, None] = "0152"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa_text(
            "UPDATE data_sources SET is_active = true "
            "WHERE code = 'suttacentral-voice' AND is_active = false"
        )
    )


def downgrade() -> None:
    op.execute(
        sa_text(
            "UPDATE data_sources SET is_active = false "
            "WHERE code = 'suttacentral-voice'"
        )
    )
