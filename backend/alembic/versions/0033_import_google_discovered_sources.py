"""import datasources discovered via Google search (Apify)

全网搜索发现的 19 个佛教数字文献数据源，覆盖：
- 梵文写本项目 (HMML, RSBMP, UTokyo)
- 藏文佛典 (PKTC, LTWA, Mandala Peking)
- 大藏经全文 (BDK, 如是佛典, 如是我闻, 大藏经在线)
- 多语种经典目录 (AIBS, 东洋文库, 东国大学)
- 巴利三藏 (PTS, Dhammayut)
- 导航聚合 (OrientNet, Nalanda Wiki)

Data discovered 2026-03-02 via Apify Google Search Scraper.

Revision ID: 0033
Revises: 0032
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = [
    # ===================================================================
    # 梵文写本项目 (Sanskrit manuscript projects)
    # ===================================================================
    {
        "code": "hmml-buddhist",
        "name_zh": "HMML 佛教与印度教写本数据库",
        "name_en": "Hill Museum & Manuscript Library - Buddhist & Hindu MSS",
        "base_url": "https://hmml.org/collections/buddhist-hindu/",
        "access_type": "external",
        "region": "美国",
        "languages": "sa,ne,bo,en",
        "description": "希尔博物馆写本图书馆，数字化保存尼泊尔/南亚佛教与印度教写本，提供高清影像与元数据检索",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
    },
    {
        "code": "rsbmp",
        "name_zh": "珍稀梵文佛教写本项目",
        "name_en": "Rare Sanskrit Buddhist Manuscripts Project",
        "base_url": "https://rsbmpproject.org/",
        "access_type": "external",
        "region": "国际",
        "languages": "sa,en",
        "description": "全球珍稀梵文佛教写本数字化与编目项目，推动学术界对新发现写本的研究与开放获取",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "utokyo-sanskrit-mss",
        "name_zh": "东京大学梵文写本数据库",
        "name_en": "UTokyo Sanskrit Manuscripts Database",
        "base_url": "https://da.dl.itc.u-tokyo.ac.jp/portal/en/collection/skt_manuscripts",
        "access_type": "external",
        "region": "日本",
        "languages": "sa,ja",
        "description": "东京大学总合图书馆所藏梵文写本数字化影像与书目数据库，含佛教经典珍贵写本",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
    },
    {
        "code": "wellcome-buddhist",
        "name_zh": "威康收藏佛教写本",
        "name_en": "Wellcome Collection Buddhist Manuscripts",
        "base_url": "https://wellcomecollection.org/",
        "access_type": "external",
        "region": "英国",
        "languages": "sa,en",
        "description": "英国威康收藏，含佛教/梵文医学写本数字化影像，支持IIIF浏览与开放检索",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": True,
        "supports_api": True,
    },
    # ===================================================================
    # 藏文佛典 (Tibetan Buddhist texts)
    # ===================================================================
    {
        "code": "pktc-tibetan-lib",
        "name_zh": "PKTC 数字藏文图书馆",
        "name_en": "Padma Karpo Translation Committee Digital Tibetan Library",
        "base_url": "https://pktc.org/digital-tibetan-library/",
        "access_type": "external",
        "region": "美国",
        "languages": "bo,en",
        "description": "白莲翻译委员会数字藏文图书馆，提供重要藏文佛典、辞典和参考工具全文",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "mandala-peking",
        "name_zh": "Mandala 北京版藏文大藏经在线",
        "name_en": "Mandala Sources - Peking Tripitaka Online",
        "base_url": "https://sources.mandala.library.virginia.edu/",
        "access_type": "external",
        "region": "美国",
        "languages": "bo,en",
        "description": "弗吉尼亚大学Mandala平台，北京版藏文大藏经(甘珠尔/丹珠尔)在线全文检索",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "tibetanlibrary-ltwa",
        "name_zh": "达兰萨拉藏文图书馆",
        "name_en": "Library of Tibetan Works and Archives",
        "base_url": "https://tibetanlibrary.org/",
        "access_type": "external",
        "region": "印度",
        "languages": "bo,en",
        "description": "达兰萨拉藏文作品与档案图书馆，含写本数字图书馆、博物馆、口述历史与影像档案",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
    },
    # ===================================================================
    # 大藏经全文 (Tripitaka full-text databases)
    # ===================================================================
    {
        "code": "bdk-daizokyo",
        "name_zh": "BDK 大藏经文本数据库",
        "name_en": "BDK Daizokyo Text Database",
        "base_url": "https://www.bdk.or.jp/bdk/digital/",
        "access_type": "external",
        "region": "日本",
        "languages": "en,lzh,ja",
        "description": "仏教伝道協会(BDK)大藏经英译全文与原文汉文对照数字数据库，可交叉查询DDB电子佛教辞典",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "rushi-ai",
        "name_zh": "如是佛典",
        "name_en": "Rushi AI Buddhist Canon",
        "base_url": "https://reader.rushi-ai.com/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "AI驱动的佛典高精度字图数据库，涵盖藏经全部原字字种，支持逐字切分标注与四种文本检索",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "rushiwowen",
        "name_zh": "如是我闻",
        "name_en": "Rushi Wowen",
        "base_url": "https://rushiwowen.co/",
        "access_type": "external",
        "region": "国际",
        "languages": "lzh,zh",
        "description": "中华大藏经总目录在线全文检索平台，提供经典原文与多版本大藏经对照功能",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "dzj-fosss",
        "name_zh": "大藏经在线阅读全文检索",
        "name_en": "Dazangjing Online Full-text Search",
        "base_url": "http://www.dzj.fosss.net/",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "description": "基于中华佛典宝库2016版的大藏经在线全文检索，含现代标点与图片链接，支持移动端",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "zojoji-daizokyo",
        "name_zh": "增上寺元版大藏经数字档案",
        "name_en": "Zojoji Temple Yuan Dynasty Tripitaka Digital Archive",
        "base_url": "https://www.jbf.ne.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh",
        "description": "净土宗大本山增上寺所藏元版大藏经数字化项目，含宋版/元版大藏经高清影像公开",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
    },
    # ===================================================================
    # 多语种经典目录 (Multi-lingual canon databases)
    # ===================================================================
    {
        "code": "aibs-canons-db",
        "name_zh": "AIBS 佛教经典研究数据库",
        "name_en": "AIBS Buddhist Canons Research Database",
        "base_url": "http://databases.aibs.columbia.edu/",
        "access_type": "external",
        "region": "美国",
        "languages": "en,sa,bo,lzh,pi",
        "description": "哥伦比亚大学AIBS维护的多语种佛教经典目录数据库，提供完整书目信息与跨传统交叉链接",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "toyobunko-butten",
        "name_zh": "东洋文库佛典书志数据库",
        "name_en": "Toyo Bunko Buddhist Texts Bibliographic Database",
        "base_url": "https://toyobunko-lab.jp/butten-shoshi/",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh,sa",
        "description": "东洋文库佛教文献书志信息与影像浏览数据库，含珍贵佛典实物影像",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": True,
        "supports_api": False,
    },
    {
        "code": "dongguk-abc",
        "name_zh": "东国大学佛学术院经典数据库",
        "name_en": "Dongguk University ABC Digital Tripitaka",
        "base_url": "https://abchome.dongguk.edu/",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,lzh,ja",
        "description": "东国大学佛学术院高丽大藏经电算化事业，含大正新修大藏经文本数据库对照",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    # ===================================================================
    # 巴利三藏 (Pali canon)
    # ===================================================================
    {
        "code": "palitextsociety",
        "name_zh": "巴利文献学会",
        "name_en": "Pali Text Society",
        "base_url": "https://palitextsociety.org/",
        "access_type": "external",
        "region": "英国",
        "languages": "pi,en",
        "description": "巴利文献学会官方网站，1882年成立，提供巴利三藏权威学术版本，部分已免费开放电子版下载",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "dhammayut-lib",
        "name_zh": "法宗派数字图书馆",
        "name_en": "Dhammayut Digital Library",
        "base_url": "https://dhammayut.org/digital-library/",
        "access_type": "external",
        "region": "泰国",
        "languages": "th,pi,en",
        "description": "泰国法宗派佛教数字图书馆，提供上座部佛教文献与修行资源",
        "supports_search": True,
        "supports_fulltext": True,
        "supports_iiif": False,
        "supports_api": False,
    },
    # ===================================================================
    # 导航聚合 (Resource aggregators)
    # ===================================================================
    {
        "code": "nalanda-wiki",
        "name_zh": "那烂陀维基",
        "name_en": "Nalanda Wiki",
        "base_url": "http://www.nalanda.kr/",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,bo,pi,lzh",
        "description": "韩国佛学数字资源维基导航，整合藏文/巴利文/汉文大藏经数字化链接与工具",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
    },
    {
        "code": "orientnet-buddhism",
        "name_zh": "OrientNet 佛教文献导航",
        "name_en": "OrientNet Buddhism Resources",
        "base_url": "https://orientnet.jp/ebuddhism.html",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,en,pi,sa,bo,lzh",
        "description": "日本东方学数字资源导航，分类整合巴利三藏/梵文/藏文/汉文佛典数据库与工具链接",
        "supports_search": False,
        "supports_fulltext": False,
        "supports_iiif": False,
        "supports_api": False,
    },
]

_ALL_CODES = [s["code"] for s in SOURCES]


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
                "code": src["code"],
                "name_zh": src["name_zh"],
                "name_en": src["name_en"],
                "base_url": src["base_url"],
                "access_type": src["access_type"],
                "region": src["region"],
                "languages": src["languages"],
                "description": src["description"],
                "supports_search": src.get("supports_search", False),
                "supports_fulltext": src.get("supports_fulltext", False),
                "supports_iiif": src.get("supports_iiif", False),
                "supports_api": src.get("supports_api", False),
            })
            inserted += 1
        else:
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
    total = conn.execute(sa_text("SELECT count(*) FROM data_sources WHERE is_active = true")).scalar()
    print(f"📊 Active sources: {total}")


def downgrade() -> None:
    conn = op.get_bind()
    for code in _ALL_CODES:
        conn.execute(sa_text("DELETE FROM data_sources WHERE code = :code"), {"code": code})
