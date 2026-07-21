"""Add data_sources.health_confidence.

``health_status`` alone cannot be shown to a reader, because the daily probe
runs from a single VPS and not every verdict survives a change of vantage. A
2026-07-21 audit of the 42 non-``ok`` sources in production found:

  - 16 ``timeout`` and 8 DNS failures — the classic signature of a datacenter
    IP being blocked, or of the prober's own resolver, not of a dead site;
  - 2 cert verdicts contradicted by the certificate itself: ``www.cnki.net``
    was recorded "Hostname mismatch" though its leaf carries ``*.cnki.net``
    (which covers it) and runs to 2027, and a Sinica host was recorded
    "certificate has expired" with a leaf valid for another month;
  - against which the genuinely actionable ones — HTTP 4xx/5xx from the server
    itself, and certs independently re-confirmed as expired (台大, 不丹) or
    issued for an unrelated name (PTS, DILA-cbc, 驹泽) — held up.

``health_confidence`` records which of those two groups a verdict is in, so a
future reader-facing badge can show the ~12 defensible ones without also
labelling live institutions as broken. Values: ``high`` | ``low``.

Defaults to ``high`` for existing rows: the column only ever *narrows* what may
be displayed, and nothing reads it yet, so backfilling optimistically keeps the
admin view unchanged until the next cron pass writes real values.

Revision ID: 0172
Revises: 0171
Create Date: 2026-07-21
"""

from alembic import op
from sqlalchemy import text

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE data_sources "
            "ADD COLUMN IF NOT EXISTS health_confidence VARCHAR(10) "
            "NOT NULL DEFAULT 'high'"
        )
    )
    op.execute(
        text(
            "COMMENT ON COLUMN data_sources.health_confidence IS "
            "'Whether the latest health verdict holds beyond the prober''s own "
            "vantage: high = server-issued HTTP status, independently "
            "re-confirmed cert fault, or a host resolving into non-public "
            "space; low = timeout / DNS failure / a cert rejection the leaf "
            "re-read did not corroborate. Only high verdicts are safe to show "
            "a reader as a fault of the source. "
            "Set by scripts/health_check_sources.py.'"
        )
    )


def downgrade() -> None:
    op.execute(text("ALTER TABLE data_sources DROP COLUMN IF EXISTS health_confidence"))
