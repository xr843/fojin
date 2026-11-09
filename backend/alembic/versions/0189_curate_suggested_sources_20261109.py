"""Curate two data sources that came in through user suggestions.

Accepting a suggestion in the admin inbox auto-created a ``data_sources`` row and
published it immediately (``is_active=True``) with only a name and the
submitter's free-text description. Two such rows needed a human pass
(2026-11-09 review of all five suggestions):

- #641 无尽藏 (mugenzo.com) — a real Chinese canon reading site (≈20,000 fascicles,
  full-text search, vernacular glosses), live since March with an empty
  description / languages / region. Fill them in.
- #950 Rooms of Light — a Nyingma practice *event calendar*, submitted by its
  own operator. Not a text or research resource, so it does not belong in the
  source catalogue; unpublish it (row kept, ``is_active=False``).

The other three suggestions were already handled: Living Gems is covered by the
curated #709 (the auto-created #708 is inactive), and the two "南传上座部中文资料大全"
rows (#710 QQ-mail relay link, #711 Baidu netdisk share) stay inactive — a
netdisk bundle of third-party translations with no verifiable licence.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0189"
down_revision: str | None = "0188"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MUGENZO_DESC = (
    "简体中文大藏经阅读站，收录近两万卷佛经，提供原文在线阅读、全文检索、"
    "AI 白话释义与关键词提示，界面有简体、繁体、日文。"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE data_sources SET name_en = :en, description = :d, languages = 'lzh,zh', "
            "region = '中国大陆', research_fields = 'han' "
            "WHERE code = 'mugenzo' AND coalesce(description, '') = ''"
        ),
        {"en": "Mugenzo Buddhist Library", "d": MUGENZO_DESC},
    )
    conn.execute(sa.text("UPDATE data_sources SET is_active = false WHERE code = 'roomsoflight'"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE data_sources SET name_en = NULL, description = NULL, languages = NULL, "
            "region = NULL, research_fields = NULL WHERE code = 'mugenzo' AND description = :d"
        ),
        {"d": MUGENZO_DESC},
    )
    conn.execute(sa.text("UPDATE data_sources SET is_active = true WHERE code = 'roomsoflight'"))
