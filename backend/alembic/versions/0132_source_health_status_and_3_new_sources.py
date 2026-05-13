"""Add data_sources.health_status + health_checked_at; backfill 25 problematic
sources from 2026-05-13 audit; add 3 new high-value sources.

Audit method: every base_url under /api/sources probed in three independent
ways — aiohttp burst, sequential curl with browser UA bypassing proxy, and
WebFetch from a US-based egress. The 25 entries below failed all three
layers, so the verdict survives any single network bias.

This migration does NOT flip is_active. is_active is for editorial removal;
a temporarily unreachable site shouldn't be silently dropped from the public
sources catalog — users come there for citation/discovery, not just to click
through. Instead we record the health state, leaving the listing intact and
letting the UI surface a "暂不可用" badge.

Three new sources added in the same migration to amortize the deploy:

  - tkh-mth-ocr  (HCIILAB Tripitaka OCR datasets — 32万字符 handwritten
                  Buddhist canon labels, foundation of EvaHan 2026 Dataset C)
  - evahan-2026  (LREC 2026 ancient-Chinese OCR shared task, Buddhist canon
                  in handwritten + mixed image-text subsets)
  - khyentse-lineage (Tsadra Wikibase covering the Khyentse lineage masters
                      and texts — distinct from existing khyentse-vision /
                      khyentse-translation entries)

Revision ID: 0132
Revises: 0131
Create Date: 2026-05-13
"""

from alembic import op
from sqlalchemy import text

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None


# Source code -> health_status. Statuses chosen:
#   unreachable   : TLS handshake stalls / ECONNREFUSED from multiple
#                   network vantages (China direct, US Anthropic node).
#                   Could be permanently dead, could be aggressive
#                   geo-fencing — either way, downstream automation
#                   can't ingest from it today.
#   cert_invalid  : Reachable but TLS chain rejected by modern browsers
#                   (expired cert, wrong SAN). Site itself is up.
HEALTH_UPDATES = {
    # === Korean .go.kr / .or.kr cluster (TLS stalls) ===
    "haeinsa": "unreachable",
    "nfm-korea": "unreachable",
    "koreanbuddhism": "unreachable",
    "nl-korea": "unreachable",
    "korcis": "unreachable",
    "nl-korea-guji": "unreachable",
    "kr-national-assembly": "unreachable",
    "dongguk-hangul-tripitaka": "cert_invalid",

    # === Japanese institutional ===
    "daito-bunka-dl": "unreachable",
    "utokyo-shuanghong": "unreachable",
    "icabs-nara-chokujo": "unreachable",
    "mahidol-tipitaka": "cert_invalid",

    # === Greater China ===
    "taiwan-buddhism-dila": "unreachable",
    "t1index-dila": "unreachable",
    "fodocs-list": "cert_invalid",
    "dunhuang-snupg": "unreachable",
    "yungang-digital": "unreachable",

    # === International / Europe / Americas ===
    "acip": "unreachable",
    "buryat-buddhism": "unreachable",
    "histochtext": "unreachable",
    "fragile-palm-leaves": "unreachable",
    "colombo-tripitaka": "unreachable",
    "bib-buddhiststudies": "unreachable",
    "mangalam-btw": "unreachable",
    "vhmml": "unreachable",
}


# New sources to add. Sort order 0 (default). All `access_type='open'`.
NEW_SOURCES = [
    {
        "code": "tkh-mth-ocr",
        "name_zh": "高丽藏+多版藏经手写体 OCR 数据集（TKH/MTH）",
        "name_en": "Tripitaka Koreana in Han + Multiple Tripitaka in Han OCR Datasets",
        "base_url": "https://github.com/HCIILAB/TKH_MTH_Datasets_Release",
        "description": "华南理工 HCIILAB 发布的两个佛教大藏经手写体识别数据集——TKH (Tripitaka Koreana in Han) 1000 张图像含约 32 万字符 23000 行，MTH (Multiple Tripitaka in Han) 覆盖中国八种藏经版本，是中文佛教典籍 OCR 与字符检测研究的基础底层数据集，亦为 EvaHan 2026 共享任务的训练数据来源。",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "research_fields": "han,dh",
        "supports_search": False,
        "has_remote_fulltext": False,
    },
    {
        "code": "evahan-2026",
        "name_zh": "EvaHan 2026 古汉语 OCR 共享任务",
        "name_en": "EvaHan 2026 — Ancient Chinese OCR Shared Tasks (LREC 2026)",
        "base_url": "https://github.com/GoThereGit/EvaHan",
        "description": "LREC 2026 与 ELRA 联合主办的第五届古汉语信息处理国际评测，2026 年聚焦多模态大模型 OCR。Dataset C 为佛教大藏经手写体子集，整合 TKH、MTH 等历代藏经写本，提供约 5000-10000 图文对训练样本，对 FoJin 标点 / 校勘 / 字图对照工作具有直接参考价值。",
        "region": "国际",
        "languages": "lzh,zh,en",
        "research_fields": "han,dh",
        "supports_search": False,
        "has_remote_fulltext": False,
    },
    {
        "code": "khyentse-lineage",
        "name_zh": "钦哲传承 Wikibase（Tsadra）",
        "name_en": "Khyentse Lineage — A Tsadra Foundation Wikibase",
        "base_url": "https://khyentselineage.tsadra.org/",
        "description": "Tsadra 基金会运营的钦哲传承（蒋扬钦哲旺波 Jamyang Khyentse Wangpo 等）人物、典籍与历史专题 Wikibase，已收录数千条藏文典籍藏威利转写与英译对照——与现有 khyentse-vision（翻译产品）和 khyentse-translation（基金会门户）互补，是研究利美运动核心人物的结构化数据入口。",
        "region": "美国",
        "languages": "bo,en",
        "research_fields": "tibetan,dh",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
]


def upgrade() -> None:
    # ---- 1. schema: health_status + health_checked_at ----
    # Plain VARCHAR (no CHECK constraint) so the cron health-monitor can
    # grow new states (e.g. 'rate_limited', 'moved') without a migration.
    # Default 'ok' means existing rows don't need explicit backfill.
    op.execute(
        text(
            "ALTER TABLE data_sources "
            "ADD COLUMN IF NOT EXISTS health_status VARCHAR(20) "
            "NOT NULL DEFAULT 'ok'"
        )
    )
    op.execute(
        text(
            "ALTER TABLE data_sources "
            "ADD COLUMN IF NOT EXISTS health_checked_at TIMESTAMPTZ"
        )
    )
    op.execute(
        text(
            "COMMENT ON COLUMN data_sources.health_status IS "
            "'Valid: ok|degraded|cert_invalid|unreachable|moved. Set by /api/admin/sources/health-check cron. Independent of is_active (which is for editorial removal).'"
        )
    )

    # ---- 2. backfill 25 entries from 2026-05-13 audit ----
    audit_ts = "2026-05-13T00:00:00+00:00"
    for code, status in HEALTH_UPDATES.items():
        op.execute(
            text(
                "UPDATE data_sources "
                f"SET health_status = '{status}', "
                f"    health_checked_at = '{audit_ts}' "
                f"WHERE code = '{code}'"
            )
        )

    # ---- 3. insert 3 new sources ----
    def q(v):
        if v is None:
            return "NULL"
        return "'" + str(v).replace("'", "''") + "'"

    for s in NEW_SOURCES:
        supports_search = "true" if s.get("supports_search") else "false"
        has_remote_fulltext = "true" if s.get("has_remote_fulltext") else "false"
        op.execute(
            text(
                "INSERT INTO data_sources "
                "(code, name_zh, name_en, base_url, description, "
                " access_type, region, languages, research_fields, "
                " supports_search, has_remote_fulltext, "
                " sort_order, is_active) "
                f"VALUES ({q(s['code'])}, {q(s['name_zh'])}, {q(s['name_en'])}, "
                f"        {q(s['base_url'])}, {q(s['description'])}, 'open', "
                f"        {q(s['region'])}, {q(s['languages'])}, {q(s['research_fields'])}, "
                f"        {supports_search}, {has_remote_fulltext}, "
                "         0, true) "
                "ON CONFLICT (code) DO NOTHING"
            )
        )


def downgrade() -> None:
    # Remove new sources first (FK-safe ordering)
    for s in NEW_SOURCES:
        op.execute(
            text(f"DELETE FROM data_sources WHERE code = '{s['code']}'")
        )
    # Reset health columns to defaults for the 25 backfilled rows
    for code in HEALTH_UPDATES:
        op.execute(
            text(
                "UPDATE data_sources "
                "SET health_status = 'ok', health_checked_at = NULL "
                f"WHERE code = '{code}'"
            )
        )
    # Drop schema additions
    op.execute(text("ALTER TABLE data_sources DROP COLUMN IF EXISTS health_checked_at"))
    op.execute(text("ALTER TABLE data_sources DROP COLUMN IF EXISTS health_status"))
