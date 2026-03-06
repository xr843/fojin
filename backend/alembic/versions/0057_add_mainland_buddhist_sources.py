"""Add mainland China Buddhist text resources and fix outdated institute URLs.

This migration focuses on the China-mainland gap identified on 2026-03-06.
It adds a set of official Buddhist text / research resources and restores the
current live URL for the CASS Institute of World Religions.

Revision ID: 0057
Revises: 0056
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    {
        "code": "fo-ancientbooks",
        "name_zh": "佛学典籍文献数据库",
        "name_en": "Buddhist Literature Database (Ancientbooks.cn)",
        "base_url": "https://fo.ancientbooks.cn/",
        "description": "中华书局 / 籍合网佛学典籍文献数据库，提供典籍浏览、检索、高级检索、专名词库与纪年换算等功能，覆盖《中华大藏经（汉文部分）》等佛学文献。",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "zh,lzh,sa,pi,bo",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "china-buddhist-academy",
        "name_zh": "中国佛学院",
        "name_en": "China Buddhist Academy",
        "base_url": "http://www.zgfxy.cn/",
        "description": "中国佛学院官方站点，覆盖佛学教育、学术活动、招生与研究动态，是大陆汉传佛教研究与人才培养的重要机构入口。",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "zh,lzh",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "china-tibetan-buddhist-academy",
        "name_zh": "中国藏语系高级佛学院",
        "name_en": "China Tibetan-language High-level Buddhist Academy",
        "base_url": "https://www.zyxgjfxy.cn/",
        "description": "中国藏语系高级佛学院官方站点，聚焦藏传佛教高级学衔、教学研究与学术活动，是大陆藏传佛教研究的重要机构入口。",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "bo,zh",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "pku-buddhism",
        "name_zh": "北京大学佛教研究中心",
        "name_en": "Peking University Buddhist Research Center",
        "base_url": "https://buddhism.pku.edu.cn/",
        "description": "北京大学佛教研究中心专题站，汇集佛教研究讲座、项目、出版与学术活动信息。",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "zh,lzh,en",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "renmin-buddhism",
        "name_zh": "中国人民大学佛教与宗教学理论研究所",
        "name_en": "Institute for the Study of Buddhism and Religious Theory, Renmin University of China",
        "base_url": "https://isbrt.ruc.edu.cn/",
        "description": "中国人民大学佛教与宗教学理论研究所专题站，提供佛教与宗教学研究动态、会议、项目与学术成果信息。",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "zh,lzh,en",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
]

SOURCE_UPDATES = [
    {
        "code": "cass-religion",
        "name_zh": "中国社科院世界宗教研究所",
        "name_en": "CASS Institute of World Religions",
        "base_url": "https://iwr.cssn.cn/",
        "description": "中国社会科学院世界宗教研究所现行官网，涵盖佛教、道教、基督宗教等宗教学研究动态、期刊与机构信息。",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "zh",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
]

SOURCE_UPDATE_ORIGINALS = [
    {
        "code": "cass-religion",
        "name_zh": "中国社科院世界宗教研究所",
        "name_en": "CASS Institute of World Religions",
        "base_url": "http://iwr.cass.cn/",
        "description": "中国社科院世界宗教研究所",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "zh",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": False,
    },
]


def _upsert_source(conn, source: dict) -> None:
    existing = conn.execute(
        sa_text("SELECT id FROM data_sources WHERE code = :code"),
        {"code": source["code"]},
    ).scalar()

    params = {
        "code": source["code"],
        "name_zh": source["name_zh"],
        "name_en": source["name_en"],
        "base_url": source["base_url"],
        "description": source["description"],
        "access_type": source["access_type"],
        "region": source["region"],
        "languages": source["languages"],
        "supports_search": source["supports_search"],
        "supports_fulltext": source["supports_fulltext"],
        "has_local_fulltext": source["has_local_fulltext"],
        "has_remote_fulltext": source["has_remote_fulltext"],
        "supports_iiif": source["supports_iiif"],
        "supports_api": source["supports_api"],
        "is_active": source["is_active"],
    }

    if existing:
        conn.execute(
            sa_text(
                """
                UPDATE data_sources SET
                    name_zh = :name_zh,
                    name_en = :name_en,
                    base_url = :base_url,
                    description = :description,
                    access_type = :access_type,
                    region = :region,
                    languages = :languages,
                    supports_search = :supports_search,
                    supports_fulltext = :supports_fulltext,
                    has_local_fulltext = :has_local_fulltext,
                    has_remote_fulltext = :has_remote_fulltext,
                    supports_iiif = :supports_iiif,
                    supports_api = :supports_api,
                    is_active = :is_active
                WHERE code = :code
                """
            ),
            params,
        )
        return

    conn.execute(
        sa_text(
            """
            INSERT INTO data_sources (
                code, name_zh, name_en, base_url, api_url, description,
                access_type, region, languages,
                supports_search, supports_fulltext,
                has_local_fulltext, has_remote_fulltext,
                supports_iiif, supports_api, is_active
            ) VALUES (
                :code, :name_zh, :name_en, :base_url, NULL, :description,
                :access_type, :region, :languages,
                :supports_search, :supports_fulltext,
                :has_local_fulltext, :has_remote_fulltext,
                :supports_iiif, :supports_api, :is_active
            )
            """
        ),
        params,
    )


def upgrade() -> None:
    conn = op.get_bind()
    for source in NEW_SOURCES:
        _upsert_source(conn, source)
    for source in SOURCE_UPDATES:
        _upsert_source(conn, source)


def downgrade() -> None:
    conn = op.get_bind()
    for source in SOURCE_UPDATE_ORIGINALS:
        _upsert_source(conn, source)
    for source in NEW_SOURCES:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": source["code"]},
        )
