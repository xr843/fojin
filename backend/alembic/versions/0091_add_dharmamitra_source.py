"""Add Dharmamitra data source.

AI-powered Buddhist text toolkit from UC Berkeley / Tsadra Foundation,
offering translation, full-text search, OCR, and Sanskrit grammar analysis
across Sanskrit, Tibetan, Classical Chinese, and 20+ output languages.

Revision ID: 0091
Revises: 0090
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0091"
down_revision: Union[str, None] = "0090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(
        sa_text("""
            INSERT INTO data_sources
                (code, name_zh, name_en, base_url, description,
                 access_type, region, languages,
                 supports_search, supports_fulltext,
                 has_local_fulltext, has_remote_fulltext,
                 supports_iiif, supports_api, is_active)
            VALUES
                (:code, :name_zh, :name_en, :base_url, :description,
                 :access_type, :region, :languages,
                 :supports_search, :supports_fulltext,
                 :has_local_fulltext, :has_remote_fulltext,
                 :supports_iiif, :supports_api, :is_active)
            ON CONFLICT (code) DO NOTHING
        """),
        {
            "code": "dharmamitra",
            "name_zh": "Dharmamitra 佛法语言AI工具",
            "name_en": "Dharmamitra — AI Toolkit for the Languages of the Dharma",
            "base_url": "https://dharmamitra.org/",
            "description": (
                "Dharmamitra——由UC Berkeley与Tsadra基金会合作开发的佛教文本AI工具平台，"
                "基于Google Gemini提供梵文、藏文、古典汉文的智能翻译、全文检索、"
                "OCR识别及梵文语法分析，支持20+语言输出。"
            ),
            "access_type": "external",
            "region": "美国",
            "languages": "sa,bo,lzh,en",
            "supports_search": True,
            "supports_fulltext": True,
            "has_local_fulltext": False,
            "has_remote_fulltext": True,
            "supports_iiif": False,
            "supports_api": True,
            "is_active": True,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa_text("DELETE FROM data_sources WHERE code = 'dharmamitra'")
    )
