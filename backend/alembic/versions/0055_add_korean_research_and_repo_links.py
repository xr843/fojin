"""Add Korean Buddhist research sources and more official GitHub links.

This migration extends the registry with a focused third-wave batch from the
2026-03-06 research pass, concentrating on:

- Korean Buddhist research institutes and electronic text initiatives
- additional official GitHub repositories for SARIT, Digital Pali Reader,
  Simsapa, and OpenPecha

Revision ID: 0055
Revises: 0054
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    {
        "code": "kibs",
        "name_zh": "韩国佛教学研究院",
        "name_en": "Korean Institute for Buddhist Studies",
        "base_url": "https://kibs.or.kr/en/",
        "description": "韩国佛教学研究院官方入口，涵盖研究活动、学术出版、讲座与韩国佛教研究社群资源。",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,en",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "dongguk-kbri",
        "name_zh": "东国大学韩国佛教研究所",
        "name_en": "Dongguk University Korean Buddhist Research Institute",
        "base_url": "https://www.dongguk.edu/eng/page/382",
        "description": "东国大学韩国佛教研究所官方页面，聚焦韩国佛教历史、汉译佛典与相关文献资料的研究与整理。",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,en,lzh",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "dongguk-ebtc",
        "name_zh": "东国大学电子佛典文化内容研究所",
        "name_en": "Dongguk Institute of Electronic Buddhist Text and Culture Content",
        "base_url": "https://www.dongguk.edu/eng/page/392",
        "description": "东国大学电子佛典文化内容研究所官方页面，推进 Hanguk Bulgyo Chonso、Hangul Tripitaka 等韩国佛教数字文本的整理、保存与公开利用。",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,en,lzh",
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
        "source_code": "sarit",
        "code": "sarit-corpus",
        "name": "SARIT Corpus Repository",
        "channel_type": "git",
        "url": "https://github.com/sarit/SARIT-corpus",
        "format": "xml/tei",
        "license_note": "SARIT 官方电子文本仓库，适合获取机器可读的梵文与印度学文本语料。",
        "is_primary_ingest": False,
        "priority": 55,
        "is_active": True,
    },
    {
        "source_code": "sarit",
        "code": "sarit-existdb",
        "name": "SARIT eXistdb App",
        "channel_type": "git",
        "url": "https://github.com/sarit/sarit-existdb",
        "format": "xquery/existdb",
        "license_note": "SARIT 官方检索应用仓库，可用于本地部署其基于 eXistdb 的文本浏览与检索界面。",
        "is_primary_ingest": False,
        "priority": 65,
        "is_active": True,
    },
    {
        "source_code": "digital-pali-reader",
        "code": "digital-pali-reader-github",
        "name": "Digital Pali Reader Repository",
        "channel_type": "git",
        "url": "https://github.com/digitalpalireader/digitalpalireader",
        "format": "html/js/txt",
        "license_note": "Digital Pali Reader 官方仓库，提供巴利语学习、三藏阅读与词典整合所需代码与文本资源。",
        "is_primary_ingest": False,
        "priority": 60,
        "is_active": True,
    },
    {
        "source_code": "simsapa-dhamma",
        "code": "simsapa-dhamma-github",
        "name": "Simsapa Dhamma Reader Repository",
        "channel_type": "git",
        "url": "https://github.com/simsapa/simsapa",
        "format": "flutter/dart/json",
        "license_note": "Simsapa Dhamma Reader 官方仓库，支持巴利文本与译文的检索、阅读与学习。",
        "is_primary_ingest": False,
        "priority": 60,
        "is_active": True,
    },
    {
        "source_code": "openpecha",
        "code": "openpecha-toolkit-v2",
        "name": "OpenPecha Toolkit v2",
        "channel_type": "git",
        "url": "https://github.com/OpenPecha/toolkit-v2",
        "format": "python/json",
        "license_note": "OpenPecha 官方 toolkit v2 仓库，用于 pecha 文本处理、标注与数据工作流。",
        "is_primary_ingest": False,
        "priority": 75,
        "is_active": True,
    },
    {
        "source_code": "openpecha",
        "code": "openpecha-webuddhist",
        "name": "WeBuddhist",
        "channel_type": "git",
        "url": "https://github.com/OpenPecha/WeBuddhist",
        "format": "typescript/web",
        "license_note": "OpenPecha 官方 WeBuddhist 仓库，面向多语佛典检索、经文关联与社区标注。",
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
