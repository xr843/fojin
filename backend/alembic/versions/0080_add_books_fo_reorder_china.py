"""Add books.fo (AI佛书网) and reorder 中国大陆 top sources.

New order:
1. cbeta-cn          (-10)  unchanged
2. dianjin           (-9)   unchanged
3. books-fo          (-8)   NEW
4. dunhuang-iiif     (-7)   unchanged
5. dunhuang-academy  (-6)   unchanged
6. yuezang           (-5)   was 0
7. qldzj             (-4)   was 0
8. hrfjw-dzj         (-3)   was -8

Revision ID: 0080
Revises: 0079
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0080"
down_revision: Union[str, None] = "0079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCE = {
    "code": "books-fo",
    "name_zh": "AI佛书网",
    "name_en": "AI Buddhist Books (books.fo)",
    "base_url": "https://books.fo/",
    "description": "佛教文档分享与AI问答平台，提供佛经、论著、历代大藏经、敦煌遗书等各类佛教文献的在线阅读、搜索与下载，并集成AI智能问答功能。",
    "access_type": "external",
    "region": "中国大陆",
    "languages": "lzh,zh",
    "supports_search": True,
    "supports_fulltext": False,
    "has_local_fulltext": False,
    "has_remote_fulltext": False,
    "supports_iiif": False,
    "supports_api": False,
    "sort_order": -8,
    "is_active": True,
}

REORDER = [
    ("yuezang", -5),
    ("qldzj", -4),
    ("hrfjw-dzj", -3),
]

ROLLBACK_ORDER = [
    ("yuezang", 0),
    ("qldzj", 0),
    ("hrfjw-dzj", -8),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Insert new source
    s = NEW_SOURCE
    conn.execute(
        sa_text("""
            INSERT INTO data_sources (
                code, name_zh, name_en, base_url, description,
                access_type, region, languages,
                supports_search, supports_fulltext,
                has_local_fulltext, has_remote_fulltext,
                supports_iiif, supports_api, sort_order, is_active
            ) VALUES (
                :code, :name_zh, :name_en, :base_url, :description,
                :access_type, :region, :languages,
                :supports_search, :supports_fulltext,
                :has_local_fulltext, :has_remote_fulltext,
                :supports_iiif, :supports_api, :sort_order, :is_active
            )
        """),
        s,
    )

    # Reorder existing sources
    for code, order in REORDER:
        conn.execute(
            sa_text("UPDATE data_sources SET sort_order = :order WHERE code = :code"),
            {"code": code, "order": order},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Restore sort orders
    for code, order in ROLLBACK_ORDER:
        conn.execute(
            sa_text("UPDATE data_sources SET sort_order = :order WHERE code = :code"),
            {"code": code, "order": order},
        )

    # Delete new source
    conn.execute(
        sa_text("DELETE FROM data_sources WHERE code = :code"),
        {"code": NEW_SOURCE["code"]},
    )
