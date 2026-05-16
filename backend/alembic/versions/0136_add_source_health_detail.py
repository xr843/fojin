"""Add data_sources.health_detail.

P1 of source-health left the health-check cron writing only a one-word verdict
(``health_status``). A ``moved`` source therefore showed a badge with no record
of *where* it moved — the redirect target lived in console logs and nowhere
else, so the verdict could not be acted on.

``health_detail`` carries the actionable context for the latest probe:

  - moved        -> the redirect target URL
  - cert_invalid -> the TLS failure reason
  - unreachable  -> the failure reason (timeout / connect / DNS / HTTP 5xx)
  - degraded     -> the HTTP status line
  - ok           -> NULL (no detail)

Nullable, no default: existing rows simply have no detail until the next cron
pass. Set by ``scripts/health_check_sources.py`` alongside ``health_status``.

Revision ID: 0136
Revises: 0135
Create Date: 2026-05-16
"""

from alembic import op
from sqlalchemy import text

revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE data_sources "
            "ADD COLUMN IF NOT EXISTS health_detail VARCHAR(500)"
        )
    )
    op.execute(
        text(
            "COMMENT ON COLUMN data_sources.health_detail IS "
            "'Actionable context for the latest health probe — redirect target "
            "for moved, failure reason otherwise, NULL when ok. "
            "Set by scripts/health_check_sources.py.'"
        )
    )


def downgrade() -> None:
    op.execute(text("ALTER TABLE data_sources DROP COLUMN IF EXISTS health_detail"))
