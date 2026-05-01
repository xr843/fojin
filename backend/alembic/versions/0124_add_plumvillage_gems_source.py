"""Add Plum Village Mindfulness Gems as a new data source.

User-requested addition (2026-05-01). Distinct from the existing
'lang-mai-archive' (plumvillage.org/library/) — /gems/ is the curated
daily-wisdom feed of Thich Nhat Hanh's short teachings, themed quote
collection. Useful as an entry-point for Engaged Buddhism / mindfulness
practitioners and shorter than full-talk archive.

Revision ID: 0124
Revises: 0123
"""

from alembic import op
from sqlalchemy import text

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None

SOURCE = {
    "code": "plumvillage-gems",
    "name_zh": "梅村正念之珠（一行禅师每日法语）",
    "name_en": "Plum Village Mindfulness Gems",
    "base_url": "https://plumvillage.org/gems/",
    "description": "梅村官方策展的一行禅师短法语合集，按正念、慈悲、相即、苦与转化等主题分类，含图文与音频，面向入世佛教与正念修习者",
    "region": "法国",
    "languages": "en,vi,fr",
    "research_fields": "han,theravada",
    "access_type": "open",
}


def upgrade() -> None:
    s = SOURCE
    name_en = f"'{s['name_en']}'" if s["name_en"] else "NULL"
    desc = s["description"].replace("'", "''")
    name_zh = s["name_zh"].replace("'", "''")
    op.execute(
        text(
            f"INSERT INTO data_sources "
            f"(code, name_zh, name_en, base_url, description, "
            f"access_type, region, languages, research_fields, sort_order, is_active) "
            f"VALUES ('{s['code']}', '{name_zh}', {name_en}, '{s['base_url']}', "
            f"'{desc}', '{s['access_type']}', '{s['region']}', "
            f"'{s['languages']}', '{s['research_fields']}', 0, true) "
            f"ON CONFLICT (code) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(text(f"DELETE FROM data_sources WHERE code = '{SOURCE['code']}'"))
