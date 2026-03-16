"""Fix dharmamitra code conflict: rename old kalavinka entry, insert new dharmamitra.org.

The existing 'dharmamitra' (id=280) actually points to kalavinka.org
(Bhikshu Dharmamitra's translation press). Rename its code to 'kalavinka'
so the new dharmamitra.org (UC Berkeley AI toolkit) can use 'dharmamitra'.

Revision ID: 0092
Revises: 0091
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0092"
down_revision: Union[str, None] = "0091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Rename old dharmamitra → kalavinka
    conn.execute(
        sa_text("""
            UPDATE data_sources
            SET code = 'kalavinka',
                name_zh = '法友翻译集 (Kalavinka)',
                name_en = 'Kalavinka Press — Bhikshu Dharmamitra Translations',
                base_url = 'https://kalavinka.org/'
            WHERE code = 'dharmamitra' AND base_url LIKE '%kalavinka%'
        """)
    )

    # Step 2: Insert new dharmamitra.org
    conn.execute(
        sa_text("""
            INSERT INTO data_sources
                (code, name_zh, name_en, base_url, description,
                 access_type, region, languages,
                 supports_search, supports_fulltext,
                 has_local_fulltext, has_remote_fulltext,
                 supports_iiif, supports_api, is_active)
            VALUES
                ('dharmamitra',
                 'Dharmamitra 佛法语言AI工具',
                 'Dharmamitra — AI Toolkit for the Languages of the Dharma',
                 'https://dharmamitra.org/',
                 'Dharmamitra——由UC Berkeley与Tsadra基金会合作开发的佛教文本AI工具平台，基于Google Gemini提供梵文、藏文、古典汉文的智能翻译、全文检索、OCR识别及梵文语法分析，支持20+语言输出。',
                 'external', '美国', 'sa,bo,lzh,en',
                 true, true, false, true, false, true, true)
            ON CONFLICT (code) DO UPDATE SET
                name_zh = EXCLUDED.name_zh,
                name_en = EXCLUDED.name_en,
                base_url = EXCLUDED.base_url,
                description = EXCLUDED.description,
                languages = EXCLUDED.languages,
                supports_search = EXCLUDED.supports_search,
                supports_fulltext = EXCLUDED.supports_fulltext,
                has_remote_fulltext = EXCLUDED.has_remote_fulltext,
                supports_api = EXCLUDED.supports_api
        """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    # Remove new dharmamitra
    conn.execute(
        sa_text("DELETE FROM data_sources WHERE code = 'dharmamitra' AND base_url LIKE '%dharmamitra.org%'")
    )
    # Restore old dharmamitra
    conn.execute(
        sa_text("""
            UPDATE data_sources
            SET code = 'dharmamitra',
                name_zh = '法友翻译集',
                name_en = 'Dharmamitra Translations',
                base_url = 'http://kalavinka.org/'
            WHERE code = 'kalavinka'
        """)
    )
