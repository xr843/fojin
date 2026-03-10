"""Add GitHub Buddhist open-source project data sources.

Adds verified, non-duplicate GitHub-hosted Buddhist studies datasets:

1. chinese-buddhism-sna  — Chinese Buddhism historical social network (18,130+ person nodes)
2. buddhist-glossaries   — Buddhist studies glossaries (47,000+ entries, CC0)
3. cltk-pali             — Classical Language Toolkit (Pali & Sanskrit NLP modules)

Deduplication notes — the following were requested but already exist in the DB
and are therefore SKIPPED:

- dpd-db          → already exists as distribution `dpd-dict-dpd-db` under `dpd-dict`
- dila-authority   → already exists as data_source `dila-authority` (0056)
                     GitHub repo DILA-edu/Authority-Databases is its data dump
- 84000-translation-memory → already exists as distribution under `84000` (0031)
- gretil-corpus    → `gretil` already in DB; gretil-corpus2/gretil-corpus returns 404
- pali-canon-class → suttacentral/pali-canon-class returns 404
- dharmamitra-nmt  → BuddhaNexus/dharmamitra-nmt returns 404;
                     `dharmamitra` already exists as data_source
- tibetan-collation (derge-kangyur) → `esukhia-kangyur` already in DB (0056/0078)
- acip-tibetan     → `acip` already in DB; Esukhia/acip-release returns 404
- open-korean-buddhism → no confirmed GitHub repo found
- lotus-sutra-corpus   → `lotus-sutra` already in DB (deactivated); no new repo found
- nikayas-sinhala      → no confirmed GitHub repo found
- buddhist-nlp-datasets → no specific confirmed repo
- sefaria-style-db     → no confirmed repo

Revision ID: 0085
Revises: 0084
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0085"
down_revision: Union[str, None] = "0084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SOURCES = [
    # ── 中国台湾 (Marcus Bingenheimer @ Temple Univ / DILA collaborator) ──
    {
        "code": "chinese-buddhism-sna",
        "name_zh": "中国佛教历史社会网络",
        "name_en": "Historical Social Network of Chinese Buddhism",
        "base_url": "https://github.com/mbingenheimer/ChineseBuddhism_SNA",
        "description": "中国佛教社会网络分析数据集，含18,130+人物节点与26,831+关系边，"
                       "跨越两千年汉传佛教史，适合知识图谱扩展与人物关系研究。"
                       "提供Gephi/Cytoscape/GEXF格式，可直接导入网络分析工具。",
        "access_type": "api",
        "region": "中国台湾",
        "languages": "lzh,en",
        "supports_api": True,
    },
    {
        "code": "buddhist-glossaries",
        "name_zh": "佛学研究术语辞典集",
        "name_en": "Buddhist Studies Glossaries",
        "base_url": "https://github.com/mbingenheimer/buddhist_studies_glossaries",
        "description": "佛学研究多语种术语表合集，含DILA佛教人名规范数据库辞典版(约47,000条)、"
                       "巴利专有名词辞典(DPPN)、瑜伽师地论梵藏汉索引等，"
                       "提供GoldenDict/StarDict等格式，CC0公共领域许可。",
        "access_type": "api",
        "region": "中国台湾",
        "languages": "lzh,en,sa,pi,bo",
        "supports_search": False,
    },
    # ── 国际 ──
    {
        "code": "cltk-pali",
        "name_zh": "经典语言处理工具包",
        "name_en": "Classical Language Toolkit (CLTK)",
        "base_url": "https://github.com/cltk/cltk",
        "description": "开源经典语言自然语言处理框架，支持巴利语与梵语的分词、词形还原、"
                       "词性标注等NLP任务，可用于佛教文本的自动化语言分析与处理。"
                       "Python库，896+ GitHub Stars。",
        "access_type": "api",
        "region": "国际",
        "languages": "pi,sa",
        "supports_api": True,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    for s in NEW_SOURCES:
        params = {
            "code": s["code"],
            "name_zh": s["name_zh"],
            "name_en": s.get("name_en", ""),
            "base_url": s["base_url"],
            "description": s.get("description", ""),
            "access_type": s.get("access_type", "api"),
            "region": s.get("region", ""),
            "languages": s.get("languages", ""),
            "supports_search": s.get("supports_search", False),
            "supports_fulltext": s.get("supports_fulltext", False),
            "has_local_fulltext": s.get("has_local_fulltext", False),
            "has_remote_fulltext": s.get("has_remote_fulltext", False),
            "supports_iiif": s.get("supports_iiif", False),
            "supports_api": s.get("supports_api", False),
            "is_active": s.get("is_active", True),
        }
        conn.execute(
            sa_text("""
                INSERT INTO data_sources (
                    code, name_zh, name_en, base_url, description,
                    access_type, region, languages,
                    supports_search, supports_fulltext,
                    has_local_fulltext, has_remote_fulltext,
                    supports_iiif, supports_api, is_active
                ) VALUES (
                    :code, :name_zh, :name_en, :base_url, :description,
                    :access_type, :region, :languages,
                    :supports_search, :supports_fulltext,
                    :has_local_fulltext, :has_remote_fulltext,
                    :supports_iiif, :supports_api, :is_active
                ) ON CONFLICT (code) DO NOTHING
            """),
            params,
        )


def downgrade() -> None:
    conn = op.get_bind()
    codes = [s["code"] for s in NEW_SOURCES]
    for code in codes:
        conn.execute(
            sa_text("DELETE FROM data_sources WHERE code = :code"),
            {"code": code},
        )
