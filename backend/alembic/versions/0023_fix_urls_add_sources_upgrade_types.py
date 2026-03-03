"""P0: fix broken URLs, merge idp duplicate; P1: add missing sources, upgrade access_types

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── P0: 修复 5 条坏 URL ──
    fixes = [
        ("putuo-lib", "https://www.putuo.org.cn/", "普陀山佛教协会官网（含佛教文化研究所）"),
        ("lingyin-temple", "https://www.lingyinsi.org/", "灵隐寺官网（含云林图书馆信息）"),
        ("dharmamitra", "http://kalavinka.org/", "Kalavinka Press 出版 Bhikshu Dharmamitra 汉传佛教经典英译"),
        ("dharma-torch", "https://dharmatorch.com/", "法炬翻译项目——目标15-20年内将《大正藏》经部翻译为英文，AI 辅助翻译"),
    ]
    for code, url, desc in fixes:
        conn.execute(sa_text(
            "UPDATE data_sources SET base_url = :url, description = :desc WHERE code = :code"
        ), {"code": code, "url": url, "desc": desc})
    print(f"✅ Fixed {len(fixes)} broken URLs")

    # P0: lotus-sutra 项目不存在，标记为 inactive
    conn.execute(sa_text(
        "UPDATE data_sources SET base_url = NULL, is_active = false, "
        "description = '此条目为占位数据，未找到对应的独立项目' WHERE code = :code"
    ), {"code": "lotus-sutra"})
    print("✅ Deactivated lotus-sutra (project does not exist)")

    # ── P0: 合并 idp + idp-bl 重复 → 保留 idp，增强数据，删 idp-bl ──
    # 先把 idp-bl 的语言信息合并到 idp
    conn.execute(sa_text(
        "UPDATE data_sources SET "
        "languages = 'sa,kho,sog,xto,txb,lzh,bo,pgd', "
        "description = '国际敦煌项目 (IDP) — 敦煌与丝路写本文献总库，含检索与 IIIF 影像浏览器', "
        "base_url = 'https://idp.bl.uk/' "
        "WHERE code = 'idp'"
    ))
    # 将 idp-bl 的 TextIdentifier 迁移到 idp
    conn.execute(sa_text(
        "UPDATE text_identifiers SET source_id = ("
        "  SELECT id FROM data_sources WHERE code = 'idp'"
        ") WHERE source_id = ("
        "  SELECT id FROM data_sources WHERE code = 'idp-bl'"
        ")"
    ))
    conn.execute(sa_text("DELETE FROM data_sources WHERE code = 'idp-bl'"))
    print("✅ Merged idp-bl into idp")

    # ── P1: 升级 access_type ──
    upgrades = [
        ("ctext", "api", "中国哲学书电子化计划——大型汉文古籍库含佛教文本，提供公开 API (ctext.org/tools/api)"),
        ("openpecha", "api", "面向藏文 pecha 的开放文本生态，提供 REST API、OCR、搜索与标注工具"),
        ("buddhanexus", "api", "跨语种佛教平行段落与互文检索平台，核心价值在相关经文/平行文献层"),
    ]
    for code, atype, desc in upgrades:
        conn.execute(sa_text(
            "UPDATE data_sources SET access_type = :atype, description = :desc WHERE code = :code"
        ), {"code": code, "atype": atype, "desc": desc})
    print(f"✅ Upgraded access_type for {len(upgrades)} sources")

    # ── P1: 补入遗漏的高价值数据源 ──
    new_sources = [
        {
            "code": "dharmacloud",
            "name_zh": "DharmaCloud 藏传佛教文献库",
            "name_en": "DharmaCloud (Tsadra Foundation)",
            "base_url": "https://dharmacloud.tsadra.org/",
            "access_type": "external",
            "region": "国际",
            "languages": "bo,en",
            "description": "Tsadra 基金会藏传佛教文献数据库，超750部文献可搜索/下载，支持按宗派和主题筛选",
        },
        {
            "code": "compassion-network",
            "name_zh": "慈悲网络数字英译大藏经",
            "name_en": "The Compassion Network Digital English Canon",
            "base_url": "https://thecompassionnetwork.org/digital-english-canon/",
            "access_type": "external",
            "region": "国际",
            "languages": "lzh,sa,en",
            "description": "三语（中/梵/英）大正藏索引，连接汉文佛教经典与现代英文翻译资源，可按大正藏编号检索",
        },
        {
            "code": "otdo",
            "name_zh": "古藏文文献在线 OTDO",
            "name_en": "Old Tibetan Documents Online",
            "base_url": "https://otdo.aa-ken.jp/",
            "access_type": "external",
            "region": "日本",
            "languages": "bo,en",
            "description": "东京外国语大学古藏文文献数据库，含282部校勘文献（7-12世纪），支持全文搜索与 KWIC 检索，链接 IIIF 影像",
        },
        {
            "code": "ltwa-resource",
            "name_zh": "西藏文献档案馆数字图书馆",
            "name_en": "Library of Tibetan Works & Archives Digital",
            "base_url": "https://ltwaresource.info/",
            "access_type": "external",
            "region": "印度",
            "languages": "bo,en",
            "description": "西藏文献与档案图书馆(LTWA)与 Emory 大学合作数字图书馆，超3000部珍稀藏传佛教手稿数字化",
        },
        {
            "code": "dtab-bonn",
            "name_zh": "波恩数字藏文档案",
            "name_en": "Digital Tibetan Archives Bonn (DTAB)",
            "base_url": "https://dtab.crossasia.org/",
            "access_type": "external",
            "region": "德国",
            "languages": "bo",
            "description": "波恩大学前现代藏文法律文书数字档案（4268件），通过 CrossAsia 平台提供检索与 IIIF 浏览",
        },
        {
            "code": "cudl-cambridge",
            "name_zh": "剑桥大学数字图书馆",
            "name_en": "Cambridge Digital Library (CUDL)",
            "base_url": "https://cudl.lib.cam.ac.uk/",
            "access_type": "external",
            "region": "英国",
            "languages": "sa,pi,en",
            "description": "剑桥大学数字图书馆，含1600多部梵文/巴利文/普拉克利特文手稿，大量佛教梵文写本（尼泊尔传承）",
        },
        {
            "code": "digital-bodleian",
            "name_zh": "牛津博德利数字图书馆",
            "name_en": "Digital Bodleian (Oxford)",
            "base_url": "https://digital.bodleian.ox.ac.uk/",
            "access_type": "external",
            "region": "英国",
            "languages": "sa,pi,bo,en",
            "description": "牛津博德利图书馆数字平台，印度次大陆以外最大梵文手稿收藏（约9000件），含佛教写本与 IIIF 影像",
        },
        {
            "code": "sanskrit-library",
            "name_zh": "梵文图书馆",
            "name_en": "The Sanskrit Library",
            "base_url": "https://sanskritlibrary.org/",
            "access_type": "external",
            "region": "美国",
            "languages": "sa,en",
            "description": "非营利梵文数字图书馆，提供数字化原始文本和计算化研究工具，涵盖三千年梵文知识传统",
        },
    ]
    inserted = 0
    for src in new_sources:
        existing = conn.execute(sa_text(
            "SELECT id FROM data_sources WHERE code = :code"
        ), {"code": src["code"]}).fetchone()
        if existing is None:
            conn.execute(sa_text(
                """INSERT INTO data_sources
                   (code, name_zh, name_en, base_url, access_type, region, languages, description, is_active)
                   VALUES (:code, :name_zh, :name_en, :base_url, :access_type, :region, :languages, :description, true)"""
            ), src)
            inserted += 1
    print(f"✅ Inserted {inserted} new high-value sources")


def downgrade() -> None:
    conn = op.get_bind()

    # Remove new sources
    new_codes = [
        "dharmacloud", "compassion-network", "otdo", "ltwa-resource",
        "dtab-bonn", "cudl-cambridge", "digital-bodleian", "sanskrit-library",
    ]
    for code in new_codes:
        conn.execute(sa_text("DELETE FROM data_sources WHERE code = :code"), {"code": code})

    # Restore access_types
    for code in ("ctext", "openpecha", "buddhanexus"):
        conn.execute(sa_text(
            "UPDATE data_sources SET access_type = 'external' WHERE code = :code"
        ), {"code": code})

    # Restore idp-bl (best effort)
    conn.execute(sa_text(
        """INSERT INTO data_sources (code, name_zh, name_en, base_url, access_type, region, languages, is_active)
           VALUES ('idp-bl', '国际敦煌项目 IDP', 'International Dunhuang Programme',
                   'https://idp.bl.uk', 'external', '国际', 'sa,kho,sog,xto,txb,lzh,bo', true)"""
    ))

    # Restore broken URLs (they were broken before, just restore the state)
    conn.execute(sa_text(
        "UPDATE data_sources SET base_url = NULL, is_active = true WHERE code = 'lotus-sutra'"
    ))
