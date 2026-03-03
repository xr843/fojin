"""supplement sources from dianjin cross-reference analysis

典津平台交叉比对补充：
- 7 个全新数据源（台北故宫/韩国学藏书阁/东大东洋文化/东文研/双红堂/俄罗斯/汉典重光）
- 6 个已有源描述增强（上海图书馆/云南/天津/浙江/首尔大学/大东文化）
- 7 个完全重复已跳过（CADAL/书格/内阁文库/巴伐利亚/启明/四川/港大）

Revision ID: 0035
Revises: 0034
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# =====================================================================
# 7 个全新数据源
# =====================================================================
NEW_SOURCES = [
    {
        "code": "taipei-npm-guji",
        "name_zh": "台北故宫古籍舆图检索系统",
        "name_en": "National Palace Museum Taipei Rare Books",
        "base_url": "https://catalog.npm.gov.tw/",
        "access_type": "external",
        "region": "中国台湾",
        "languages": "lzh",
        "description": "台北故宫博物院善本古籍与舆图检索系统，含2,291条珍贵古籍影像记录，包括佛教写经/木刻经/官刻经等",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "kr-aks-jangseogak",
        "name_zh": "韩国学中央研究院数字藏书阁",
        "name_en": "Academy of Korean Studies Jangseogak Digital Archive",
        "base_url": "https://jsg.aks.ac.kr/",
        "access_type": "external",
        "region": "韩国",
        "languages": "ko,lzh",
        "description": "韩国学中央研究院藏书阁数字典藏，23,186条古籍记录含大量佛教文献，提供高清影像浏览与目录检索",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "utokyo-toyo-bunka",
        "name_zh": "东京大学东洋文化研究所汉籍善本影像库",
        "name_en": "UTokyo Institute for Advanced Studies on Asia Rare Chinese Books",
        "base_url": "https://shanben.ioc.u-tokyo.ac.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "description": "东京大学东洋文化研究所所藏汉籍善本全文影像资料库，3,889条记录含佛教典籍/注疏/写经影像",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "utokyo-tobunken-nlc",
        "name_zh": "日本东文研汉籍影像库",
        "name_en": "UTokyo Toyo Bunko Chinese Classics Images (NLC)",
        "base_url": "http://read.nlc.cn/allSearch/searchList?searchType=6",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "description": "东京大学东洋文化研究所汉籍影像收入中华古籍资源库，3,731条高清影像记录含佛教典籍",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "utokyo-shuanghong",
        "name_zh": "东京大学双红堂文库影像库",
        "name_en": "UTokyo Shuanghong Library Digital Collection",
        "base_url": "https://shuanghong.ioc.u-tokyo.ac.jp/",
        "access_type": "external",
        "region": "日本",
        "languages": "lzh,ja",
        "description": "东京大学东洋文化研究所双红堂文库，收藏长�的近代中国宗教/民俗出版物，3,365条记录含佛教刊物/佛教杂志/经文",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": True, "supports_api": False,
    },
    {
        "code": "russian-nel-guji",
        "name_zh": "俄罗斯国家电子图书馆古籍",
        "name_en": "National Electronic Library of Russia (Chinese Rare Books)",
        "base_url": "https://rusneb.ru/",
        "access_type": "external",
        "region": "俄罗斯",
        "languages": "lzh,ru",
        "description": "俄罗斯国家电子图书馆所藏汉籍古籍数字化，409条记录含敦煌/西域佛教写本及中国古代佛教典籍",
        "supports_search": True, "supports_fulltext": False,
        "supports_iiif": False, "supports_api": False,
    },
    {
        "code": "hdcg-wenyuan",
        "name_zh": "汉典重光古籍平台",
        "name_en": "Han Dian Chong Guang (Ancient Texts Revived)",
        "base_url": "https://wenyuan.aliyun.com/hdcg",
        "access_type": "external",
        "region": "中国大陆",
        "languages": "lzh",
        "description": "阿里达摩院与四川大学合作AI修复古籍项目，利用深度学习修复破损古籍，180条记录含佛经修复件，提供全文检索",
        "supports_search": True, "supports_fulltext": True,
        "supports_iiif": False, "supports_api": False,
    },
]

# =====================================================================
# 6 个已有源增强更新
# =====================================================================
UPDATES = [
    {
        "code": "shanghai-lib",
        "description": "上海图书馆古籍善本数字化平台，10,794条记录涵盖宋元明清善本，含大量佛教典籍/碑帖/写经影像，部分需注册访问",
        "supports_search": True,
    },
    {
        "code": "yunnan-lib",
        "description": "云南省图书馆古籍数字化，9,995条记录含南传佛教贝叶经/汉传佛教典籍/少数民族文字佛经，云南佛教传统深厚覆盖南传与汉传",
        "supports_search": True,
    },
    {
        "code": "tianjin-lib",
        "description": "天津图书馆古籍数字资源，6,642条记录收入中华古籍资源库，含佛教藏经/刻本/抄本，完全开放访问",
        "supports_search": True,
    },
    {
        "code": "zhejiang-lib",
        "description": "浙江省图书馆古籍与浙江省历史文献数字资源总库，2,829条记录含天台宗/禅宗等浙江佛教文献，完全开放",
        "supports_search": True,
    },
    {
        "code": "snu-lib-guji",
        "description": "韩国首尔大学图书馆善本古籍数字化，1,502条记录含高丽/朝鲜时代佛教典籍善本影像，完全开放",
        "supports_search": True,
    },
    {
        "code": "daito-bunka-dl",
        "description": "日本大东文化大学数字图书馆，1,223条汉籍记录含儒学/佛教/经史古典籍影像，大东文化大学有深厚中国学研究传统",
        "supports_search": True,
    },
]

_NEW_CODES = [s["code"] for s in NEW_SOURCES]
_UPDATE_CODES = [u["code"] for u in UPDATES]


def upgrade() -> None:
    conn = op.get_bind()
    inserted = 0
    updated = 0

    # 插入新源
    for src in NEW_SOURCES:
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
            updated += 1

    # 更新已有源
    enriched = 0
    for upd in UPDATES:
        conn.execute(sa_text(
            """UPDATE data_sources SET
               description = :description,
               supports_search = supports_search OR :supports_search
               WHERE code = :code"""
        ), {
            "code": upd["code"],
            "description": upd["description"],
            "supports_search": upd.get("supports_search", False),
        })
        enriched += 1

    print(f"✅ Inserted {inserted} new sources, skipped {updated} existing")
    print(f"📝 Enriched {enriched} existing source descriptions")
    total = conn.execute(sa_text("SELECT count(*) FROM data_sources WHERE is_active = true")).scalar()
    print(f"📊 Active sources: {total}")


def downgrade() -> None:
    conn = op.get_bind()
    for code in _NEW_CODES:
        conn.execute(sa_text("DELETE FROM data_sources WHERE code = :code"), {"code": code})
    # 恢复原始描述 (best effort, 不可完全恢复)
    for upd in UPDATES:
        conn.execute(sa_text(
            "UPDATE data_sources SET description = '' WHERE code = :code"
        ), {"code": upd["code"]})
