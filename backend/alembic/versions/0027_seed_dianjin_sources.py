"""seed sources discovered from 典津 (guji.cckb.cn) platform audit

Revision ID: 0027
Revises: 0026
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = [
    # ===== 聚合平台 =====
    {
        "code": "dianjin",
        "name_zh": "典津·全球汉籍影像开放集成系统",
        "name_en": "Dian Jin - Global Chinese Classics Image System",
        "base_url": "https://guji.cckb.cn/",
        "access_type": "api",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "清华大学 AI 驱动古籍聚合平台，72.8万条元数据覆盖128机构14国，提供开放 API",
        "supports_search": True,
        "supports_api": True,
    },
    {
        "code": "shidianguji",
        "name_zh": "识典古籍",
        "name_en": "Shidian Guji (ByteDance)",
        "base_url": "https://www.shidianguji.com/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "北大-字节跳动联合开发古籍 OCR 全文平台，2.56万部古籍含儒释道核心典籍，OCR 准确率 96-97%",
        "supports_search": True,
        "supports_fulltext": True,
    },
    {
        "code": "cadal",
        "name_zh": "CADAL 大学数字图书馆",
        "name_en": "China Academic Digital Associative Library",
        "base_url": "https://cadal.edu.cn/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "中国高等教育数字图书馆国际合作计划，291万卷含24万卷古籍影像（含佛教类），需高校 IP 或注册账号",
        "supports_search": True,
    },
    {
        "code": "hathitrust",
        "name_zh": "HathiTrust 数字图书馆",
        "name_en": "HathiTrust Digital Library",
        "base_url": "https://www.hathitrust.org/",
        "access_type": "api",
        "region": "美国",
        "languages": "en,lzh,sa,bo,ja,ko",
        "description": "美国大型数字图书馆联盟，1780万数字化卷册含佛教学术著作/大藏经影印，公共域可全文阅读，提供 API",
        "supports_search": True,
        "supports_api": True,
    },
    # ===== 图书馆/档案 =====
    {
        "code": "nl-korea",
        "name_zh": "韩国国立中央图书馆",
        "name_en": "National Library of Korea",
        "base_url": "https://www.nl.go.kr/",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,lzh",
        "description": "韩国最大图书馆，古籍综合目录(KORCIS)收录63,583种善本含中国本古籍1,930种、高丽藏相关文献",
        "supports_search": True,
    },
    {
        "code": "naikaku-bunko",
        "name_zh": "日本国立公文書館(内阁文库)",
        "name_en": "National Archives of Japan - Cabinet Library",
        "base_url": "https://www.digital.archives.go.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh",
        "description": "内阁文库继承江户城红叶山文库等旧藏，含大量汉籍佛典数字化影像，约1/4馆藏已数字化可在线浏览",
        "supports_search": True,
        "supports_iiif": True,
    },
    {
        "code": "kokusho-nijl",
        "name_zh": "国文学研究资料馆·国书数据库",
        "name_en": "NIJL Kokusho Database",
        "base_url": "https://kokusho.nijl.ac.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh",
        "description": "日本古典籍综合数据库，江户时代以前古典籍书目与高清影像含和刻佛经/写本，支持 IIIF 浏览",
        "supports_search": True,
        "supports_iiif": True,
    },
    {
        "code": "tianyige",
        "name_zh": "天一阁古籍数字化平台",
        "name_en": "Tianyige Digital Classics",
        "base_url": "https://gj.tianyige.com.cn/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh",
        "description": "中国最古老私人藏书楼数字化平台，340万页古籍扫描开放2万余册近3000部善本（含部分佛教方志/寺志）",
        "supports_search": True,
    },
    # ===== 大藏经版本 =====
    {
        "code": "zhaocheng-jinzang",
        "name_zh": "赵城金藏",
        "name_en": "Zhaocheng Jin Canon",
        "base_url": "http://read.nlc.cn/thematDataSearch/toGujiIndex",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh",
        "description": "金代民间募刻大藏经（以《开宝藏》为底本），现存最早刻本大藏经之一，国图已发布1,281种4,000余卷影像",
        "supports_search": True,
        "supports_iiif": True,
    },
    {
        "code": "yongle-beizang",
        "name_zh": "永乐北藏",
        "name_en": "Yongle Northern Canon",
        "base_url": "http://read.nlc.cn/thematDataSearch/toGujiIndex",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh",
        "description": "明永乐年间官刻大藏经（北京版），国图已发布5,050册18.6万拍约55万页高清影像",
        "supports_search": True,
        "supports_iiif": True,
    },
    {
        "code": "grandsutras",
        "name_zh": "GrandSutras 大藏经 PDF",
        "name_en": "GrandSutras",
        "base_url": "http://grandsutras.org/",
        "access_type": "external",
        "region": "国际",
        "languages": "lzh",
        "description": "多版本大藏经（永乐北藏、嘉兴藏等）PDF 下载站",
        "supports_fulltext": True,
    },
    # ===== 佛学专业工具 =====
    {
        "code": "neidian-baike",
        "name_zh": "内典百科",
        "name_en": "Neidian Baike (Buddhist Encyclopaedia)",
        "base_url": "https://baike.yuezang.org/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "佛教典籍百科，40个分类含题解/注疏/异译本/译经者数据库，CC BY-SA 4.0 许可",
        "supports_search": True,
    },
    {
        "code": "yixing-dict",
        "name_zh": "一行佛学辞典",
        "name_en": "Yixing Buddhist Dictionary",
        "base_url": "https://buddhaspace.org/dict/",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh,zh",
        "description": "台大狮子吼佛学专站维护，整合13部佛学辞典（丁福保/佛光/中华佛教百科/一切经音义等）",
        "supports_search": True,
    },
    # ===== 导航平台 =====
    {
        "code": "wenxianxue",
        "name_zh": "奎章阁·中国古典文献资源导航",
        "name_en": "Wenxianxue.cn Classical Literature Navigation",
        "base_url": "https://www.wenxianxue.cn/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "清华大学团队维护的古籍数字资源导航系统，含佛教专题分类（CBETA/大正藏/赵城金藏/永乐藏等导航）",
        "supports_search": True,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    inserted = 0
    updated = 0
    for src in SOURCES:
        code = src["code"]
        existing = conn.execute(
            sa_text("SELECT id FROM data_sources WHERE code = :code"),
            {"code": code},
        ).fetchone()
        if existing is None:
            conn.execute(sa_text(
                """INSERT INTO data_sources
                   (code, name_zh, name_en, base_url, access_type, region, languages,
                    description, supports_search, supports_fulltext, supports_iiif, supports_api, is_active)
                   VALUES (:code, :name_zh, :name_en, :base_url, :access_type, :region, :languages,
                           :description, :supports_search, :supports_fulltext, :supports_iiif, :supports_api, true)"""
            ), {
                **src,
                "supports_search": src.get("supports_search", False),
                "supports_fulltext": src.get("supports_fulltext", False),
                "supports_iiif": src.get("supports_iiif", False),
                "supports_api": src.get("supports_api", False),
            })
            inserted += 1
        else:
            # Update existing with better data
            conn.execute(sa_text(
                """UPDATE data_sources SET
                   description = :description,
                   supports_search = supports_search OR :supports_search,
                   supports_fulltext = supports_fulltext OR :supports_fulltext,
                   supports_iiif = supports_iiif OR :supports_iiif,
                   supports_api = supports_api OR :supports_api
                   WHERE code = :code"""
            ), {
                "code": code,
                "description": src["description"],
                "supports_search": src.get("supports_search", False),
                "supports_fulltext": src.get("supports_fulltext", False),
                "supports_iiif": src.get("supports_iiif", False),
                "supports_api": src.get("supports_api", False),
            })
            updated += 1
    print(f"✅ Inserted {inserted} new sources, updated {updated} existing")

    # Print final stats
    total = conn.execute(sa_text("SELECT count(*) FROM data_sources WHERE is_active = true")).scalar()
    searchable = conn.execute(sa_text("SELECT count(*) FROM data_sources WHERE supports_search = true AND is_active = true")).scalar()
    print(f"📊 Active: {total}, Searchable: {searchable}")


def downgrade() -> None:
    conn = op.get_bind()
    codes = [s["code"] for s in SOURCES]
    for code in codes:
        conn.execute(sa_text("DELETE FROM data_sources WHERE code = :code"), {"code": code})
