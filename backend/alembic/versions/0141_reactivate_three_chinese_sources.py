"""Reactivate three Chinese sources confirmed back after a temporary outage.

Migration 0138 retired four sources whose homepages were unconfigured-host
placeholders ("Site is created successfully!"). Three of them —
shu-fo (佛书网), xuefo (学点佛), 51shu (无忧索引) — were only temporarily
down; the site owner has confirmed they are back with real content, so they
return to the public catalog.

The fourth from 0138, gandhari-scrolls (ebmp.org), stays retired — its domain
was sold off, a permanent loss.

health_status is deliberately left at 'cert_invalid': all three sites
currently serve an expired TLS certificate (verified 2026-05-17). is_active
flips them back into the catalog; the health badge keeps honestly flagging
the cert until it is renewed. is_active and health_status are independent by
design (see migration 0132).

Revision ID: 0141
Revises: 0140
Create Date: 2026-05-17
"""

from alembic import op
from sqlalchemy import text

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None

RESTORED_SOURCES = ("shu-fo", "xuefo", "51shu")


def _set_active(active: bool) -> None:
    # RESTORED_SOURCES are fixed ASCII slugs — safe to inline, and an inline
    # IN-list renders under `alembic --sql` offline mode (a bound list does not).
    codes = ", ".join(f"'{c}'" for c in RESTORED_SOURCES)
    value = "true" if active else "false"
    op.execute(text(f"UPDATE data_sources SET is_active = {value} WHERE code IN ({codes})"))


def upgrade() -> None:
    _set_active(True)


def downgrade() -> None:
    _set_active(False)
