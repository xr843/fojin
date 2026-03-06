"""Add specialized Buddhist text sources from global web research.

This migration adds 12 vetted sources discovered via hands-on global web
research on 2026-03-06, focusing on:

- DILA / CHIBS topic databases with direct Buddhist text coverage
- Japanese canon / manuscript databases from ICABS, Toyo Bunko, and UTokyo
- an overseas university open manuscript portal
- one GitHub-hosted open Tibetan corpus

It also attaches 4 GitHub source_distributions to existing sources so the
project can expose official open repositories alongside institution portals.

Revision ID: 0052
Revises: 0051
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    {
        "code": "ybh-dila",
        "name_zh": "瑜伽师地论数据库",
        "name_en": "Yogacarabhumi Database",
        "base_url": "https://ybh.dila.edu.tw/",
        "description": "法鼓文理学院佛教数字资源中心维护的《瑜伽师地论》专题数据库，提供全文浏览与检索。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,sa,zh",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "sdp-dila",
        "name_zh": "多语种法华经数据库",
        "name_en": "Lotus Sutra in Many Languages Database",
        "base_url": "https://sdp.dila.edu.tw/",
        "description": "DILA / CHIBS 多语种《法华经》专题数据库，整合汉文、梵文及多语种版本。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,sa,en,ja,ko,zh",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "vmtd-dila",
        "name_zh": "唯识典籍数字资料库",
        "name_en": "Digital Database for Vijnaptimatrata Texts",
        "base_url": "https://vmtd.dila.edu.tw/",
        "description": "法鼓文理学院唯识学专题库，汇集唯识相关佛典、注疏与研究资料。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,sa,zh",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "hysc-dila",
        "name_zh": "华严经疏钞数字平台",
        "name_en": "Avatamsaka Sutra Commentary Database",
        "base_url": "https://hysc.dila.edu.tw/",
        "description": "DILA《新修华严经疏钞数字平台》，面向《华严经》注疏文本的专题整理与检索。",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,zh",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "icabs-koshakyo",
        "name_zh": "日本古写经数据库",
        "name_en": "Japanese Old Manuscripts of Buddhist Scriptures Database",
        "base_url": "https://koshakyo-database.icabs.ac.jp/",
        "description": "国际佛教学大学院大学（ICABS）古写经专题数据库，提供日本古写经编目与检索。",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "icabs-nara-chokujo",
        "name_zh": "奈良朝敕定一切经数据库",
        "name_en": "Nara-period Imperially Commissioned Buddhist Canons Database",
        "base_url": "https://nara-chokyo.icabs.ac.jp/",
        "description": "ICABS 奈良朝敕定一切经专题数据库，聚焦日本古代一切经编目与版本信息。",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "u-renja-jiaxing",
        "name_zh": "友莲嘉兴藏数据库",
        "name_en": "Yurenja Jiaxing Edition Buddhist Canon Database",
        "base_url": "https://u-renja.toyobunko-lab.jp/",
        "description": "东洋文库友莲嘉兴藏数据库，提供嘉兴版大藏经专题整理与检索入口。",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "taishozo-teihonkohon",
        "name_zh": "大正藏底本校本数据库",
        "name_en": "Taishozo Teihonkohon Database",
        "base_url": "https://taishozo-teihonkohon.toyobunko-lab.jp/",
        "description": "东洋文库大正藏底本校本数据库，支持对照《大正藏》与底本、校本信息。",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "utokyo-jiaxing-canon",
        "name_zh": "东京大学嘉兴藏数字档案",
        "name_en": "UTokyo Digital Jiaxing Canon",
        "base_url": "https://da.dl.itc.u-tokyo.ac.jp/portal/en/collection/kasyozou",
        "description": "东京大学附属图书馆公开的嘉兴藏数字档案，提供高清影像与 IIIF 浏览。",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "utokyo-tengyur-catalog",
        "name_zh": "东京大学纳塘版丹珠尔卡片目录数据库",
        "name_en": "UTokyo Narthang Tengyur Card Catalog Database",
        "base_url": "https://da.dl.itc.u-tokyo.ac.jp/portal/en/collection/narthan",
        "description": "东京大学附属图书馆公开的纳塘版丹珠尔卡片目录数据库，适合藏文大藏经目录检索。",
        "access_type": "external",
        "region": "日本",
        "languages": "bo,ja",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "openn-upenn",
        "name_zh": "宾大 OPenn 开放写本库",
        "name_en": "OPenn Manuscripts (University of Pennsylvania)",
        "base_url": "https://openn.library.upenn.edu/",
        "description": "宾夕法尼亚大学图书馆开放手稿平台，提供包含佛教梵文手稿在内的高清影像、TEI/XML 与开放下载。",
        "access_type": "external",
        "region": "美国",
        "languages": "sa,bo,lzh,en",
        "supports_search": True,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "classical-tibetan-corpus",
        "name_zh": "古典藏文语料库",
        "name_en": "Classical Tibetan Corpus",
        "base_url": "https://github.com/tibetan-nlp/classical-tibetan-corpus",
        "description": "GitHub 开源古典藏文语料库，提供机器可读文本、标注与研究用语料，适合藏文 NLP 与佛典数字研究。",
        "access_type": "external",
        "region": "国际",
        "languages": "bo,en",
        "supports_search": True,
        "supports_fulltext": True,
        "has_local_fulltext": False,
        "has_remote_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
]

SOURCE_DISTRIBUTIONS = [
    {
        "source_code": "dpd-dict",
        "code": "dpd-dict-dpd-db",
        "name": "DPD Database Repository",
        "channel_type": "git",
        "url": "https://github.com/digitalpalidictionary/dpd-db",
        "format": "sqlite/csv",
        "license_note": "Digital Pali Dictionary 官方数据库仓库，适合词典同步与离线研究。",
        "is_primary_ingest": False,
        "priority": 40,
        "is_active": True,
    },
    {
        "source_code": "buddhanexus",
        "code": "buddhanexus-segmented-sanskrit",
        "name": "Segmented Sanskrit Repository",
        "channel_type": "git",
        "url": "https://github.com/BuddhaNexus/segmented-sanskrit",
        "format": "txt/json",
        "license_note": "BuddhaNexus 官方梵文切分语料仓库，可作为跨文本比较与对齐研究补充。",
        "is_primary_ingest": False,
        "priority": 60,
        "is_active": True,
    },
    {
        "source_code": "openpecha",
        "code": "openpecha-botok",
        "name": "Botok",
        "channel_type": "git",
        "url": "https://github.com/OpenPecha/Botok",
        "format": "python",
        "license_note": "OpenPecha 官方藏文分词与文本处理工具仓库，适合藏文文本预处理。",
        "is_primary_ingest": False,
        "priority": 70,
        "is_active": True,
    },
    {
        "source_code": "buda",
        "code": "buda-tibetan-ocr-app",
        "name": "Tibetan OCR App",
        "channel_type": "git",
        "url": "https://github.com/buda-base/tibetan-ocr-app",
        "format": "python",
        "license_note": "BUDA / BDRC 官方藏文 OCR 应用仓库，可辅助影像到文本的研究流程。",
        "is_primary_ingest": False,
        "priority": 70,
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


def _upsert_distribution(conn, item: dict) -> None:
    source_id = conn.execute(
        sa_text("SELECT id FROM data_sources WHERE code = :code"),
        {"code": item["source_code"]},
    ).scalar()
    if source_id is None:
        return

    existing = conn.execute(
        sa_text("SELECT id FROM source_distributions WHERE code = :code"),
        {"code": item["code"]},
    ).scalar()

    params = {
        "source_id": source_id,
        "code": item["code"],
        "name": item["name"],
        "channel_type": item["channel_type"],
        "url": item["url"],
        "format": item["format"],
        "license_note": item["license_note"],
        "is_primary_ingest": item["is_primary_ingest"],
        "priority": item["priority"],
        "is_active": item["is_active"],
    }

    if existing:
        conn.execute(
            sa_text(
                """
                UPDATE source_distributions SET
                    source_id = :source_id,
                    name = :name,
                    channel_type = :channel_type,
                    url = :url,
                    format = :format,
                    license_note = :license_note,
                    is_primary_ingest = :is_primary_ingest,
                    priority = :priority,
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
            INSERT INTO source_distributions (
                source_id, code, name, channel_type, url, format,
                license_note, is_primary_ingest, priority, is_active
            ) VALUES (
                :source_id, :code, :name, :channel_type, :url, :format,
                :license_note, :is_primary_ingest, :priority, :is_active
            )
            """
        ),
        params,
    )


def upgrade() -> None:
    conn = op.get_bind()
    for source in NEW_SOURCES:
        _upsert_source(conn, source)
    for item in SOURCE_DISTRIBUTIONS:
        _upsert_distribution(conn, item)


def downgrade() -> None:
    conn = op.get_bind()

    for item in SOURCE_DISTRIBUTIONS:
        conn.execute(
            sa_text("DELETE FROM source_distributions WHERE code = :code"),
            {"code": item["code"]},
        )

    for source in NEW_SOURCES:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": source["code"]},
        )
