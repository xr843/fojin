"""Add 51shu.app (无忧索引 / Ashoka Index) data source.

Buddhist resource file index platform with public search API,
indexing sutras, audio, video, images, and documents across
multiple cloud storage collections.

Revision ID: 0093
Revises: 0092
Create Date: 2026-03-17
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0093"
down_revision: Union[str, None] = "0092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(
        sa_text("""
            INSERT INTO data_sources
                (code, name_zh, name_en, base_url, api_url, description,
                 access_type, region, languages,
                 supports_search, supports_fulltext,
                 has_local_fulltext, has_remote_fulltext,
                 supports_iiif, supports_api, is_active)
            VALUES
                (:code, :name_zh, :name_en, :base_url, :api_url, :description,
                 :access_type, :region, :languages,
                 :supports_search, :supports_fulltext,
                 :has_local_fulltext, :has_remote_fulltext,
                 :supports_iiif, :supports_api, :is_active)
            ON CONFLICT (code) DO UPDATE SET
                name_zh = EXCLUDED.name_zh,
                name_en = EXCLUDED.name_en,
                base_url = EXCLUDED.base_url,
                api_url = EXCLUDED.api_url,
                description = EXCLUDED.description,
                supports_search = EXCLUDED.supports_search,
                supports_api = EXCLUDED.supports_api
        """),
        {
            "code": "51shu",
            "name_zh": "无忧索引",
            "name_en": "Ashoka Index",
            "base_url": "https://51shu.app/",
            "api_url": "https://api.51shu.app/search",
            "description": (
                "无忧索引（Ashoka Index）——佛教资源极速索引平台，"
                "聚合网盘、文档、辞典、CBETA等多来源佛教文件，"
                "提供经文、音频、视频、图片、电子书等资源的全文搜索，"
                "仅提供索引不存储文件。"
            ),
            "access_type": "api",
            "region": "中国大陆",
            "languages": "lzh,zh",
            "supports_search": True,
            "supports_fulltext": False,
            "has_local_fulltext": False,
            "has_remote_fulltext": False,
            "supports_iiif": False,
            "supports_api": True,
            "is_active": True,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa_text("DELETE FROM data_sources WHERE code = '51shu'")
    )
