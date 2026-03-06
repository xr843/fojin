"""Ensure OpenPecha source exists and attach Botok distribution.

The running database was found to be missing the `openpecha` top-level source,
which caused the `openpecha-botok` GitHub distribution added in 0052 to be
skipped. This migration restores the source and guarantees the distribution.

Revision ID: 0054
Revises: 0053
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPENPECHA_SOURCE = {
    "code": "openpecha",
    "name_zh": "OpenPecha 开放藏文",
    "name_en": "OpenPecha",
    "base_url": "https://openpecha.org/",
    "description": "开放协作藏文文本数字化平台，提供机器可读 pecha 文本、OCR、搜索与标注生态。",
    "access_type": "api",
    "region": "国际",
    "languages": "bo",
    "supports_search": True,
    "supports_fulltext": True,
    "has_local_fulltext": False,
    "has_remote_fulltext": True,
    "supports_iiif": False,
    "supports_api": True,
    "is_active": True,
}

BOTOK_DISTRIBUTION = {
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
}


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
    _upsert_source(conn, OPENPECHA_SOURCE)
    _upsert_distribution(conn, BOTOK_DISTRIBUTION)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa_text("DELETE FROM source_distributions WHERE code = :code"),
        {"code": BOTOK_DISTRIBUTION["code"]},
    )
    conn.execute(
        sa_text("DELETE FROM data_sources WHERE code = :code"),
        {"code": OPENPECHA_SOURCE["code"]},
    )
