"""Retire two defunct sources confirmed dead by the 2026-06-01 source audit.

Verified by independent browser-UA probes from two vantages (a residential
egress AND the in-VPS cron's Singapore egress) plus a web search for a current
URL — not the single-vantage cron alone, which over-reports unreachable for
live sites that block datacenter IPs.

DEFUNCT — retired via is_active=false (row kept; re-addable later if a stable
public URL appears):

  hdcg-wenyuan   wenyuan.aliyun.com   (汉典重光 / 阿里达摩院海外古籍数字化平台)
                 The 2021 research project was officially wound down; the host
                 now returns 404 at every path. A successor exists in spirit —
                 识典古籍 (北大 + 字节跳动) — but at a different project/URL, so
                 it is a separate "add source" decision, not a URL repoint.

  t1index-dila   dev.dila.edu.tw/t1index/  (长阿含经注解索引数据库)
                 Lives only on DILA's *dev* subdomain, which fails the TLS
                 handshake from every vantage. A curated directory should not
                 link a staging host; retired pending a confirmed production
                 URL (then re-add under the usual "add sources" migration).

Mirrors migration 0144's idiom: is_active (editorial removal) and health_status
(cron reachability) stay independent — this migration only flips is_active.

Revision ID: 0146
Revises: 0145
Create Date: 2026-06-01
"""

from alembic import op
from sqlalchemy import text

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None

# Domains confirmed defunct / staging-only — retired from the public catalog.
DEFUNCT_SOURCES = (
    "hdcg-wenyuan",
    "t1index-dila",
)


def _set_active(active: bool) -> None:
    # Fixed ASCII slugs — safe to inline so the statement renders under
    # `alembic --sql` offline mode (a bound IN-list does not).
    codes = ", ".join(f"'{c}'" for c in DEFUNCT_SOURCES)
    value = "true" if active else "false"
    op.execute(text(f"UPDATE data_sources SET is_active = {value} WHERE code IN ({codes})"))


def upgrade() -> None:
    _set_active(False)


def downgrade() -> None:
    _set_active(True)
