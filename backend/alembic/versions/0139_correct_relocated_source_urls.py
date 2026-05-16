"""Correct base_url for three sources whose pages relocated.

From the 2026-05-16 content audit: these institutions are alive and well, but
their old base_url no longer reaches the resource. Each new URL was verified
by hand to return the intended content:

  sotozen-global       global.sotozen.com ("無効なURLです" — dead path)
                       -> www.sotozen.com/eng/  (official multilingual site)
  dhammachai-tipitaka  www.dhammachai.org (an unconfigured site template)
                       -> www.dhammachaitipitaka.org/  (the DTP project site)
  komazawa-zenpon      www.komazawa-u.ac.jp/.../collection/ (404)
                       -> repo.komazawa-u.ac.jp/.../collections/
                          (駒澤大学 電子貴重書庫 — the Zen rare-book repository)

Revision ID: 0139
Revises: 0138
Create Date: 2026-05-16
"""

from alembic import op
from sqlalchemy import text

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None

# code -> (old_base_url, new_base_url)
URL_UPDATES = {
    "sotozen-global": ("https://global.sotozen.com/", "https://www.sotozen.com/eng/"),
    "dhammachai-tipitaka": (
        "https://www.dhammachai.org/",
        "https://www.dhammachaitipitaka.org/",
    ),
    "komazawa-zenpon": (
        "https://www.komazawa-u.ac.jp/facilities/library/collection/",
        "https://repo.komazawa-u.ac.jp/repo/repository/collections/",
    ),
}


def _set_base_url(code: str, url: str) -> None:
    op.execute(
        text("UPDATE data_sources SET base_url = :u WHERE code = :c").bindparams(u=url, c=code)
    )


def upgrade() -> None:
    for code, (_old, new) in URL_UPDATES.items():
        _set_base_url(code, new)


def downgrade() -> None:
    for code, (old, _new) in URL_UPDATES.items():
        _set_base_url(code, old)
