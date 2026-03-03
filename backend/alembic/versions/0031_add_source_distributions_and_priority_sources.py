"""add source_distributions and seed priority ingest endpoints

P0: attach official git / bulk distribution endpoints to core sources
    (CBETA / SuttaCentral / 84000)
P1: add Asian Legacy Library as a new top-level source
P2: add Sacred Texts Buddhism as a low-priority supplemental source
P3: intentionally exclude shadow-library style sources (e.g. Z-Library)

Revision ID: 0031
Revises: 0030
Create Date: 2026-03-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    {
        "code": "asian-legacy-library",
        "name_zh": "亚洲典籍图书馆",
        "name_en": "Asian Legacy Library",
        "base_url": "https://www.asianlegacylibrary.org/",
        "description": "开放佛教写本与古籍资源库，提供公共领域数字资源与下载入口。",
        "access_type": "external",
        "region": "国际",
        "languages": "bo,sa,lzh",
        "supports_search": False,
        "supports_fulltext": False,
        "has_local_fulltext": False,
        "has_remote_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "sacred-texts",
        "name_zh": "Sacred Texts 佛教文献",
        "name_en": "Sacred Texts: Buddhism",
        "base_url": "https://sacred-texts.com/bud/index.htm",
        "description": "公共领域英译佛教文本集合，适合作为长尾补充阅读源，不建议作为核心版本学主源。",
        "access_type": "external",
        "region": "国际",
        "languages": "en",
        "supports_search": False,
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
        "source_code": "cbeta",
        "code": "cbeta-cbdata-fulltext",
        "name": "CBData Fulltext",
        "channel_type": "bulk_dump",
        "url": "https://cbdata.dila.edu.tw/fulltext",
        "format": "txt/xml",
        "license_note": "CBETA 官方全文下载入口；使用需遵循 CBETA 与站点条款。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    {
        "source_code": "cbeta",
        "code": "cbeta-xml-p5",
        "name": "CBETA XML P5",
        "channel_type": "git",
        "url": "https://github.com/cbeta-org/xml-p5",
        "format": "xml",
        "license_note": "CBETA 官方 XML P5 主文本仓；推荐作为主导入源。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "cbeta",
        "code": "cbeta-xml-p5a",
        "name": "CBETA XML P5a",
        "channel_type": "git",
        "url": "https://github.com/cbeta-git/xml-p5a",
        "format": "xml",
        "license_note": "内部工作版本，仅作次级参考，不建议作为对外主源。",
        "is_primary_ingest": False,
        "priority": 30,
        "is_active": True,
    },
    {
        "source_code": "cbeta",
        "code": "cbeta-tafxml",
        "name": "CBETA TAFxml",
        "channel_type": "git",
        "url": "https://github.com/DILA-edu/CBETA_TAFxml",
        "format": "xml",
        "license_note": "适合补充结构化层级、版式与导入稳定性。",
        "is_primary_ingest": False,
        "priority": 40,
        "is_active": True,
    },
    {
        "source_code": "cbeta",
        "code": "cbeta-metadata",
        "name": "CBETA Metadata",
        "channel_type": "git",
        "url": "https://github.com/DILA-edu/cbeta-metadata",
        "format": "csv/json",
        "license_note": "适合补充经录、规范化映射与导入元数据。",
        "is_primary_ingest": False,
        "priority": 50,
        "is_active": True,
    },
    {
        "source_code": "suttacentral",
        "code": "suttacentral-bilara-data",
        "name": "Bilara Data",
        "channel_type": "git",
        "url": "https://github.com/suttacentral/bilara-data",
        "format": "json",
        "license_note": "当前更适合持续同步的主数据仓，适合多语文本与分段对齐。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "suttacentral",
        "code": "suttacentral-sc-data",
        "name": "SC Data (legacy)",
        "channel_type": "git",
        "url": "https://github.com/suttacentral/sc-data",
        "format": "json",
        "license_note": "历史数据仓，已标注 deprecated；仅作兼容与历史补充。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    {
        "source_code": "84000",
        "code": "84000-data-tei",
        "name": "84000 Data TEI",
        "channel_type": "git",
        "url": "https://github.com/84000/data-tei",
        "format": "tei/xml",
        "license_note": "开放数据仓；使用与展示需遵循 84000 Terms of Use。",
        "is_primary_ingest": True,
        "priority": 10,
        "is_active": True,
    },
    {
        "source_code": "84000",
        "code": "84000-data-rdf",
        "name": "84000 Data RDF",
        "channel_type": "git",
        "url": "https://github.com/84000/data-rdf",
        "format": "rdf",
        "license_note": "适合知识图谱、实体映射与术语关系抽取。",
        "is_primary_ingest": False,
        "priority": 20,
        "is_active": True,
    },
    {
        "source_code": "84000",
        "code": "84000-translation-memory",
        "name": "84000 Translation Memory",
        "channel_type": "git",
        "url": "https://github.com/84000/data-translation-memory",
        "format": "tmx/csv",
        "license_note": "翻译记忆数据；需留意仓库内的单独许可说明。",
        "is_primary_ingest": False,
        "priority": 30,
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
    else:
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


def _insert_distribution(conn, item: dict) -> None:
    source_id = conn.execute(
        sa_text("SELECT id FROM data_sources WHERE code = :code"),
        {"code": item["source_code"]},
    ).scalar()
    if source_id is None:
        raise RuntimeError(f"Missing data_sources row for code={item['source_code']}")

    existing = conn.execute(
        sa_text("SELECT id FROM source_distributions WHERE code = :code"),
        {"code": item["code"]},
    ).scalar()
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
            {
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
            },
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
        {
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
        },
    )


def upgrade() -> None:
    op.create_table(
        "source_distributions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("channel_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("format", sa.String(length=50), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("is_primary_ingest", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa_text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_source_distribution_code"),
    )
    op.create_index("ix_source_distributions_source_id", "source_distributions", ["source_id"])

    conn = op.get_bind()

    for source in NEW_SOURCES:
        _upsert_source(conn, source)

    for item in SOURCE_DISTRIBUTIONS:
        _insert_distribution(conn, item)


def downgrade() -> None:
    op.drop_index("ix_source_distributions_source_id", table_name="source_distributions")
    op.drop_table("source_distributions")

    conn = op.get_bind()
    for source in NEW_SOURCES:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": source["code"]},
        )
