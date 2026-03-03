"""import datasources from comprehensive global research

综合多源搜集发现的 16 个新佛教数字文献数据源：
- 学术LibGuides策展 (普林斯顿/多伦多/耶鲁/ANU/ASU等6所大学)
- OrientNet/Nalanda Wiki 日韩资源导航
- Wikipedia 佛教文本/大藏经条目外链
- GitHub 佛教文本开源仓库

覆盖：缅甸写本、东南亚铭文、喜马拉雅珍本、巴利藏越译、
高丽大藏经数据集、15国巴利平行语料、京大汉文佛典等

Revision ID: 0034
Revises: 0033
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = [
    # ===================================================================
    # 东南亚写本与铭文 (Southeast Asian manuscripts & epigraphy)
    # ===================================================================
    {
        "code": "inya-archive",
        "name_zh": "Inya学院缅甸写本数字档案",
        "name_en": "Inya Institute Digital Archive",
        "base_url": "https://archive-inyainstitute.org/",
        "access_type": "external",
        "region": "缅甸",
        "languages": "my,pi,en",
        "description": "缅甸Inya学院数字化写本/器物/绘画/照片档案，含佛教贝叶经与写本集",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "mmdl-myanmar",
        "name_zh": "缅甸写本数字图书馆",
        "name_en": "Myanmar Manuscript Digital Library (UofT)",
        "base_url": "https://mmdl.utoronto.ca/",
        "access_type": "external",
        "region": "加拿大",
        "languages": "my,pi,en",
        "description": "多伦多大学主持的缅甸写本数字图书馆，来自缅甸各地图书馆的写本与珍稀版本影像",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "sealang-epigraphy",
        "name_zh": "SEAlang 东南亚铭文数据库",
        "name_en": "SEAlang Inscription Database",
        "base_url": "http://sealang.net/",
        "access_type": "external",
        "region": "国际",
        "languages": "sa,pi,km,th,my,en",
        "description": "东南亚佛教/印度教碑铭数据库与多语言辞典工具集，覆盖高棉/泰/缅等语种",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "efeo-angkor-inscriptions",
        "name_zh": "法国远东学院柬埔寨铭文库",
        "name_en": "EFEO Inventory of Cambodian Inscriptions",
        "base_url": "https://cik.efeo.fr/",
        "access_type": "external",
        "region": "法国",
        "languages": "sa,pi,km,fr",
        "description": "法国远东学院吴哥/柬埔寨梵文与巴利文佛教碑铭编目与影像",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "vietnamese-nikaaya",
        "name_zh": "越南尼柯耶(巴利经藏越译)",
        "name_en": "Vietnamese Nikaaya Buddhist Canon",
        "base_url": "http://www.buddhist-canon.com/PALI/VIET/",
        "access_type": "external",
        "region": "越南",
        "languages": "vi,pi",
        "description": "巴利经藏越南语全文译本，上座部佛教越南语传统",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    # ===================================================================
    # 喜马拉雅/藏传 (Himalayan & Tibetan)
    # ===================================================================
    {
        "code": "digital-himalaya",
        "name_zh": "数字喜马拉雅珍本文库",
        "name_en": "Digital Himalaya Rare Books",
        "base_url": "http://www.digitalhimalaya.com/collections/rarebooks/",
        "access_type": "external",
        "region": "英国",
        "languages": "bo,ne,sa,en",
        "description": "剑桥/耶鲁合作的喜马拉雅地区珍稀文献扫描件，含藏文/尼泊尔语佛教典籍/辞典/写本PDF",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "dharma-ebooks",
        "name_zh": "Dharma Ebooks 藏传佛典仓库",
        "name_en": "Dharma Ebooks",
        "base_url": "https://dharmaebooks.org/",
        "access_type": "external",
        "region": "国际",
        "languages": "bo,en",
        "description": "藏传佛教经典与哲学文本电子书库，提供全文下载与在线阅读",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "sakya-digital-lib",
        "name_zh": "萨迦数字图书馆",
        "name_en": "A Sakya Digital Library",
        "base_url": "http://www.sakyalibrary.com/",
        "access_type": "external",
        "region": "国际",
        "languages": "bo,en",
        "description": "萨迦派藏传佛教数字图书馆，提供萨迦传承文献与经典全文",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    # ===================================================================
    # 上座部/巴利 (Theravada & Pali)
    # ===================================================================
    {
        "code": "bps-online",
        "name_zh": "佛教出版社在线文库",
        "name_en": "Buddhist Publication Society Online Library",
        "base_url": "http://www.bps.lk/",
        "access_type": "external",
        "region": "斯里兰卡",
        "languages": "en,pi",
        "description": "斯里兰卡佛教出版社开放文库，提供Wheel/Bodhi Leaf等系列上座部佛教权威出版物全文",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "jataka-edinburgh",
        "name_zh": "爱丁堡大学本生故事数据库",
        "name_en": "Jataka Stories Database (Edinburgh)",
        "base_url": "https://jatakastories.div.ed.ac.uk/",
        "access_type": "external",
        "region": "英国",
        "languages": "en,pi,sa",
        "description": "爱丁堡大学本生故事可检索数据库，含佛陀前世故事的印度文本与艺术作品影像",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    # ===================================================================
    # 日本数字档案 (Japanese digital archives)
    # ===================================================================
    {
        "code": "ryukoku-u-archives",
        "name_zh": "龙谷大学佛教数字档案",
        "name_en": "Ryukoku University Digital Archives",
        "base_url": "http://www.afc.ryukoku.ac.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,lzh",
        "description": "龙谷大学佛教与亲鸾研究数字典藏，含珍贵佛教写本/版本影像",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "nii-digital-silk-road",
        "name_zh": "NII 数字丝绸之路项目",
        "name_en": "NII Digital Silk Road Project",
        "base_url": "http://dsr.nii.ac.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "ja,en",
        "description": "日本国立情报学研究所数字丝绸之路，含东洋文库探险记录与珍贵佛教写本影像",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "zinbun-kyoto-chinese-buddhist",
        "name_zh": "京大人文研中国佛典数据库",
        "name_en": "Kyoto University Zinbun Chinese Buddhist Texts WWW DB",
        "base_url": "http://kanji.zinbun.kyoto-u.ac.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "description": "京都大学人文科学研究所中文佛典WWW数据库，提供汉文佛典全文检索",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    # ===================================================================
    # 梵文 & 英译 (Sanskrit & English translations)
    # ===================================================================
    {
        "code": "clay-sanskrit",
        "name_zh": "Clay 梵文文库",
        "name_en": "Clay Sanskrit Library",
        "base_url": "https://claysanskritlibrary.org/",
        "access_type": "external",
        "region": "美国",
        "languages": "sa,en",
        "description": "经典梵文文学双语对照文库，含佛教相关梵文原典与英译",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "btts-sutra-texts",
        "name_zh": "佛经翻译委员会经典文本",
        "name_en": "Buddhist Text Translation Society Sutra Texts",
        "base_url": "http://www.cttbusa.org/",
        "access_type": "external",
        "region": "美国",
        "languages": "en,lzh",
        "description": "宣化上人创办的佛经翻译委员会经典英译全文，含楞严经/法华经/华严经等重要经典",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
    # ===================================================================
    # 开源数据集 (Open datasets from GitHub)
    # ===================================================================
    {
        "code": "pali-tripitaka-15lang",
        "name_zh": "15国巴利大藏经平行语料库",
        "name_en": "Pali Tripitaka 15-Country Parallel Corpus",
        "base_url": "https://github.com/x39826/Pali_Tripitaka",
        "access_type": "api",
        "region": "国际",
        "languages": "pi,th,my,si,km,lo,en,zh",
        "description": "15国巴利大藏经平行语料库与多语言机器翻译系统，含巴利/泰/缅/僧/高棉/老挝/英/中文对照",
        "supports_search": False, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
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
