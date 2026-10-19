"""Retire the two 「南传上座部中文资料大全」 rows (``pan`` / ``wx``).

Both were added on 2026-05-02 and point at personal file shares rather than a
publishing site: ``pan`` is a Baidu netdisk share link with its extraction code
in the URL, ``wx`` a QQ-mail share page. Their descriptions read like forwarded
chat messages, and ``wx`` says the bundle holds "北大版巴利三藏等几乎所有版本的
巴利三藏中文版" — published translations that are very likely still in copyright.
Whether this particular bundle infringes was not verified, but the trade is
lopsided: a public directory linking to it carries the risk, while the two rows
drew 5 clicks in 13 weeks (Umami, 2026-07-20 ~ 10-18).

Site owner approved retirement on 2026-10-19. As in 0178/0183, ``is_active =
FALSE``; nothing is deleted and ``downgrade`` restores both rows.

Revision ID: 0184
Revises: 0183
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0184"
down_revision: str | None = "0183"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RETIRED_CODES = ("pan", "wx")


def _set_active(active: bool) -> None:
    op.execute(
        sa_text("UPDATE data_sources SET is_active = :active WHERE code = ANY(:codes)").bindparams(
            active=active, codes=list(RETIRED_CODES)
        )
    )


def upgrade() -> None:
    _set_active(False)


def downgrade() -> None:
    _set_active(True)
