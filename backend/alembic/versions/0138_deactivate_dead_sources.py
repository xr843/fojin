"""Deactivate four dead sources found in the 2026-05-16 content audit.

The health check audits reachability; this content audit fetched each active
source's homepage title and found four whose sites no longer exist — they
answer HTTP 200, so the reachability cron cannot catch them, but the page is
a domain-sale or unconfigured-host placeholder:

  gandhari-scrolls  ebmp.org    -> "Sold by Seo.Domains" (domain sold off)
  51shu             51shu.app   -> "Site is created successfully!" (empty host)
  shu-fo            shu.fo      -> "Site is created successfully!" (empty host)
  xuefo             xue.fo      -> "Site is created successfully!" (empty host)

is_active=false retires them from the public catalog; base_url is left intact
for the record. Same treatment as suttaworld / deerpark-ai in migration 0137.

Revision ID: 0138
Revises: 0137
Create Date: 2026-05-16
"""

from alembic import op
from sqlalchemy import text

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None

DEAD_SOURCES = ("gandhari-scrolls", "51shu", "shu-fo", "xuefo")


def _set_active(active: bool) -> None:
    op.execute(
        text("UPDATE data_sources SET is_active = :a WHERE code = ANY(:codes)").bindparams(
            a=active, codes=list(DEAD_SOURCES)
        )
    )


def upgrade() -> None:
    _set_active(False)


def downgrade() -> None:
    _set_active(True)
