"""Add xue.fo (学点佛) data source.

Revision ID: 0109
Revises: 0108
"""

from alembic import op
from sqlalchemy import text

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text("""
        INSERT INTO data_sources (code, name_zh, name_en, base_url, description,
                                  access_type, region, languages, research_fields,
                                  supports_search, sort_order, is_active)
        VALUES ('xuefo', '学点佛', 'Xue.fo', 'https://xue.fo/',
                '佛学资源导航网站，聚合全球40余个佛教数字资源，涵盖大藏经、佛学辞典、电子书、影音、论文库、OCR工具等，覆盖汉传、藏传、南传、梵文多传统',
                'open', '中国大陆', 'zh,lzh', 'dh',
                false, 0, true)
        ON CONFLICT (code) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.execute(text("DELETE FROM data_sources WHERE code = 'xuefo'"))
