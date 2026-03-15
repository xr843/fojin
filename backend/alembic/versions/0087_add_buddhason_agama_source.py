"""Add 莊春江讀經站 (Buddhason Agama) data source.

Zhuang Chunjiang's Agama Reading Station — a comprehensive platform for
comparative study of Agama sutras and Pali Nikaya texts with Chinese translations,
Pali originals, and scholarly commentary.

Contains 8 major collections (~7,000+ texts):
  - 4 Agamas: SA (1362), MA (222), DA (30), AA (470)
  - 4 Nikayas: SN (~2900), MN (152), DN (34), AN (~1764)
  - 15+ Khuddaka texts: Ud, It, Dh, Su, Th, Ti, Ja, etc.

Revision ID: 0087
Revises: 0086
Create Date: 2026-03-15
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0087"
down_revision: Union[str, None] = "0086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
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
            "code": "buddhason",
            "name_zh": "莊春江讀經站",
            "name_en": "Zhuang Chunjiang Agama Reading Station",
            "base_url": "https://agama.buddhason.org/",
            "description": (
                "莊春江居士主持的阿含经南北传对读平台，"
                "提供四阿含（雜/中/長/增壹）与四部（相应/中/长/增支）的"
                "汉译对照、巴利原文及南北传经文比对注释。"
                "涵盖约7000+经文，是早期佛教文献比较研究的重要资源。"
            ),
            "access_type": "external",
            "region": "台湾",
            "languages": "lzh,pi",
            "supports_search": False,
            "supports_fulltext": True,
            "has_local_fulltext": False,
            "has_remote_fulltext": True,
            "supports_iiif": False,
            "supports_api": False,
            "is_active": True,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa_text("DELETE FROM data_sources WHERE code = 'buddhason'")
    )
