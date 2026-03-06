"""Add a second wave of specialized Buddhist text sources.

This migration extends the source registry with 10 more vetted resources
identified during a second global search pass on 2026-03-06, focusing on:

- DILA / Buddhist Informatics special-purpose databases
- Pali / Theravada research portals and canon platforms

It also corrects the existing `dila-glossaries` record so it points to the
actual glossaries platform rather than the separate authority database.

Revision ID: 0053
Revises: 0052
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    {
        "code": "cbc-dila",
        "name_zh": "汉文佛典著者数据库",
        "name_en": "Chinese Buddhist Canonical Attributions",
        "base_url": "https://cbc.dila.edu.tw/cbc/",
        "description": "DILA / PBD 维护的汉文佛典著者归属数据库，适合检索经录、作者与文本归属关系。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,sa,bo,pi,en",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "mavb-dila",
        "name_zh": "中边分别论数据库",
        "name_en": "Madhyanta-vibhaga-bhasya Database",
        "base_url": "https://mavb.dila.edu.tw/",
        "description": "DILA《中边分别论》专题数据库，提供梵汉文本与研究辅助检索。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "sa,lzh,zh,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "buddhistlexicon-dila",
        "name_zh": "佛教辞汇数字学习平台",
        "name_en": "Buddhist Lexicon Digital Learning Platform",
        "base_url": "https://buddhistlexicon.dila.edu.tw/",
        "description": "DILA 佛教辞汇平台，整合佛学辞汇、术语解析、XML/CSV 下载与数字人文教学工具。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,sa,pi,zh,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": True,
        "is_active": True,
    },
    {
        "code": "taiwan-buddhism-dila",
        "name_zh": "台湾佛教数字博物馆",
        "name_en": "Digital Archives of Taiwan Buddhism",
        "base_url": "https://taiwanbuddhism.dila.edu.tw/",
        "description": "台湾佛教数字典藏与博物馆平台，整合文献、图像、人物与历史研究资源。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "zh,lzh,ja,en",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "taiwan-fojiao-dila",
        "name_zh": "《台湾佛教》期刊数字典藏",
        "name_en": "Taiwan Buddhism Journal Digital Archive",
        "base_url": "https://buddhistinformatics.dila.edu.tw/taiwan_fojiao/",
        "description": "《台湾佛教》期刊专题数字典藏，适合检索近现代台湾佛教史料与期刊全文。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "zh",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "minguo-journals-dila",
        "name_zh": "民国佛教期刊书目数据库",
        "name_en": "Republican Era Buddhist Periodicals Bibliographic Database",
        "base_url": "https://buddhistinformatics.dila.edu.tw/minguofojiaoqikan/",
        "description": "DILA 民国佛教期刊书目数据库，适合追踪近现代佛教期刊、篇目与传播史。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "zh",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "t1index-dila",
        "name_zh": "长阿含经注解索引数据库",
        "name_en": "T1Index Modern Annotated Dirgha Agama Index",
        "base_url": "https://dev.dila.edu.tw/t1index/",
        "description": "DILA《现代语译长阿含经注解索引》平台，提供 HTML / PDF / XML 形式的研究索引资源。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,zh,ja",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "tipitaka-hall",
        "name_zh": "Tipitaka Hall 云端巴利藏",
        "name_en": "Tipitaka Hall Cloud Pali Canon",
        "base_url": "https://www.tptk.org/cloud/",
        "description": "泰国 Tipitaka Hall 提供的云端巴利三藏与多版本佛典阅读平台。",
        "access_type": "external",
        "region": "泰国",
        "languages": "pi,th,my,si,km,lo,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "pali-translation",
        "name_zh": "巴利翻译项目",
        "name_en": "Pali Translation Project",
        "base_url": "https://palitranslation.org/",
        "description": "以 Pali 文本英译与术语讨论为核心的开放项目，适合追踪当代巴利翻译成果。",
        "access_type": "external",
        "region": "英国",
        "languages": "pi,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "pali-hub",
        "name_zh": "Pali Hub 巴利研究书目库",
        "name_en": "Pali Hub",
        "base_url": "https://www.palihub.org/",
        "description": "牛津佛学研究中心支持的巴利研究书目门户，覆盖图书、论文与数字资源索引。",
        "access_type": "external",
        "region": "英国",
        "languages": "pi,en",
        "supports_search": True,
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
        "code": "dila-glossaries",
        "name_zh": "DILA 佛学辞汇与术语平台",
        "name_en": "DILA Buddhist Glossaries",
        "base_url": "https://glossaries.dila.edu.tw/",
        "description": "DILA 佛学辞汇与术语平台，提供佛学术语查询、解析工具与可下载词汇数据。",
        "access_type": "api",
        "region": "中国台湾",
        "languages": "lzh,zh,sa,pi,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": True,
        "is_active": True,
    },
]

SOURCE_UPDATE_ORIGINALS = [
    {
        "code": "dila-glossaries",
        "name_zh": "DILA 佛学规范术语",
        "name_en": "DILA Buddhist Authority Databases",
        "base_url": "https://authority.dila.edu.tw/",
        "description": "DILA 佛学规范资料库（人名、地名、时间、术语权威数据）",
        "access_type": "api",
        "region": "台湾",
        "languages": "lzh,zh,sa,pi,en",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": True,
        "is_active": True,
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
    for source in NEW_SOURCES:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": source["code"]},
        )
    for source in SOURCE_UPDATE_ORIGINALS:
        _upsert_source(conn, source)
