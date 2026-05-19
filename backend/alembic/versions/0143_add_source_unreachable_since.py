"""Add data_sources.unreachable_since.

source-health P2: the daily digest needs to flag sources that have been
*continuously* unreachable long enough to consider deactivating. ``health_status``
only records the latest verdict, so the start of an unreachable streak was
unknowable — "down for 30 days" could not be computed.

``unreachable_since`` marks when a source first entered its current unreachable
streak. ``scripts/health_check_sources.py`` sets it on the first unreachable
probe, keeps it across consecutive unreachable probes, and clears it (NULL) on
any other verdict. ``now() - unreachable_since`` is then the streak length.

Nullable, no default: a source not currently unreachable simply has NULL. The
next cron pass populates it for any source already unreachable.

Revision ID: 0143
Revises: 0142
Create Date: 2026-05-19
"""

from alembic import op
from sqlalchemy import text

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE data_sources "
            "ADD COLUMN IF NOT EXISTS unreachable_since TIMESTAMPTZ"
        )
    )
    op.execute(
        text(
            "COMMENT ON COLUMN data_sources.unreachable_since IS "
            "'When the source first entered its current continuous unreachable "
            "streak; NULL when not unreachable. Set by "
            "scripts/health_check_sources.py.'"
        )
    )


def downgrade() -> None:
    op.execute(
        text("ALTER TABLE data_sources DROP COLUMN IF EXISTS unreachable_since")
    )
