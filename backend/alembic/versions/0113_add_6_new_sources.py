"""Add 6 new data sources from xue.fo cross-reference.

Revision ID: 0113
Revises: 0112
"""

from alembic import op
from sqlalchemy import text

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None

SOURCES = [
    {
        "code": "shu-fo",
        "name_zh": "佛书网",
        "name_en": None,
        "base_url": "https://shu.fo/",
        "description": "佛教电子书在线阅读与下载平台，收录20余万篇佛学文档，提供PDF等格式检索与下载",
        "region": "中国大陆",
        "languages": "zh,lzh",
        "research_fields": "han",
        "access_type": "open",
    },
    {
        "code": "dict-fo",
        "name_zh": "佛学辞典",
        "name_en": None,
        "base_url": "https://dict.fo/",
        "description": "在线佛学辞典，界面美观、词库丰富，提供佛教术语与名相的查询与释义",
        "region": "中国大陆",
        "languages": "zh,lzh",
        "research_fields": "dictionary",
        "access_type": "open",
    },
    {
        "code": "budaedu",
        "name_zh": "佛陀教育基金会",
        "name_en": "Buddha Educational Foundation",
        "base_url": "https://www.budaedu.org/",
        "description": "台湾佛教基金会，免费印赠佛经善书，提供经书电子档下载与多语种佛典资源",
        "region": "中国台湾",
        "languages": "zh,lzh,en",
        "research_fields": "han",
        "access_type": "open",
    },
    {
        "code": "fodian-net",
        "name_zh": "中华佛典宝库",
        "name_en": None,
        "base_url": "http://www.fodian.net/",
        "description": "数字化佛典宝库，收录大藏经、藏外典籍、佛学词典，含音像法宝下载",
        "region": "中国大陆",
        "languages": "zh,lzh,en",
        "research_fields": "han",
        "access_type": "open",
    },
    {
        "code": "kandianguji",
        "name_zh": "看典古籍",
        "name_en": None,
        "base_url": "https://www.kandianguji.com/",
        "description": "一站式古籍数字化平台，提供古籍阅读、检索、OCR识别与校对服务",
        "region": "中国大陆",
        "languages": "zh,lzh",
        "research_fields": "dh",
        "access_type": "open",
    },
    {
        "code": "rushi-guji-tools",
        "name_zh": "如是古籍工具集",
        "name_en": None,
        "base_url": "https://guji.rushi-ai.net/",
        "description": "AI驱动的古籍数字化工具，提供OCR、智能标点、标点迁移与多文本比对功能",
        "region": "中国大陆",
        "languages": "zh,lzh",
        "research_fields": "dh",
        "access_type": "open",
    },
]


def upgrade() -> None:
    for s in SOURCES:
        name_en = f"'{s['name_en']}'" if s["name_en"] else "NULL"
        op.execute(
            text(
                f"INSERT INTO data_sources "
                f"(code, name_zh, name_en, base_url, description, "
                f"access_type, region, languages, research_fields, sort_order, is_active) "
                f"VALUES ('{s['code']}', '{s['name_zh']}', {name_en}, '{s['base_url']}', "
                f"'{s['description']}', '{s['access_type']}', '{s['region']}', "
                f"'{s['languages']}', '{s['research_fields']}', 0, true) "
                f"ON CONFLICT (code) DO NOTHING"
            )
        )


def downgrade() -> None:
    codes = ", ".join(f"'{s['code']}'" for s in SOURCES)
    op.execute(text(f"DELETE FROM data_sources WHERE code IN ({codes})"))
