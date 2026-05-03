"""Add 8 text/scripture-focused Buddhist data sources.

Filling six clear gaps in FoJin's coverage:
  - Sanskrit Buddhist manuscripts (largest private collection): Schøyen
  - Korean Won Buddhism (3rd largest Korean tradition): Wŏnbulgyo Scripture
  - Japanese Nichiren / Soka Gakkai (Lotus Sutra English): Nichiren Library
  - Pure Land English scholarship (Shinran): Collected Works of Shinran
  - Chinese Buddhism US diaspora (Hsuan Hua lineage): CTTB
  - Tibetan minor lineages: Drikung Kagyu, Jonang (Tāranātha)
  - Theravada UK forest tradition (Ajahn Chah lineage): Forest Sangha

All eight are scripture / dharma-text archives — no art-only museums in
this batch. URLs verified reachable 2026-05-03.

Revision ID: 0125
Revises: 0124
"""

from alembic import op
from sqlalchemy import text

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None

SOURCES = [
    # === Sanskrit manuscripts ===
    {
        "code": "schoyen-collection",
        "name_zh": "舍恩写本收藏（佛教写本部分）",
        "name_en": "The Schøyen Collection (Buddhist Manuscripts)",
        "base_url": "https://www.schoyencollection.com/",
        "description": "私人收藏全球最大的梵语佛教残叶库，含巴米扬、吉尔吉特出土早期大乘经典写本，由 Jens Braarvig 团队编目数百种残片",
        "region": "挪威",
        "languages": "sa,en",
        "research_fields": "sanskrit,dh",
        "supports_search": True,
        "has_remote_fulltext": False,
    },

    # === Korean Won Buddhism ===
    {
        "code": "won-buddhism-scripture",
        "name_zh": "圆佛教正典韩英对照",
        "name_en": "Won Buddhism Scripture (Wŏnbulgyo Kyosŏ)",
        "base_url": "http://wonscripture.org/",
        "description": "韩国圆佛教（Wŏnbulgyo）官方经典在线版，含《正典》《大宗经》韩英对照全文与逐句检索，是韩国本土第三大佛教教派核心文献入口",
        "region": "韩国",
        "languages": "ko,en,lzh",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },

    # === Japanese Nichiren / SGI ===
    {
        "code": "nichiren-library",
        "name_zh": "日莲佛教文库",
        "name_en": "Nichiren Buddhism Library",
        "base_url": "https://www.nichirenlibrary.org/",
        "description": "创价学会国际中心运营，日莲遗文（Gosho）+ 法华经 + 摩诃止观英译全集与 Soka Gakkai Dictionary，日莲宗与创价学会研究英语界标准底本",
        "region": "日本",
        "languages": "en,ja,lzh",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },

    # === Japanese Pure Land (English scholarship) ===
    {
        "code": "shinran-cws",
        "name_zh": "亲鸾全集英译（CWS）",
        "name_en": "The Collected Works of Shinran (CWS Online)",
        "base_url": "https://shinranworks.com/",
        "description": "西本愿寺国际中心官方授权的亲鸾全集英译在线版（Hirota 等译），是英语圈研究净土真宗祖师亲鸾的标准底本",
        "region": "美国",
        "languages": "en,ja",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },

    # === Chinese Buddhism US diaspora ===
    {
        "code": "cttb-usa",
        "name_zh": "万佛圣城（宣化上人）",
        "name_en": "City of Ten Thousand Buddhas (CTTB)",
        "base_url": "https://www.cttbusa.org/",
        "description": "宣化上人创立的万佛圣城与法界佛教总会官方数字经藏：华严、楞严、法华全本汉英对照及宣化讲解英译，海外汉传佛教 diaspora 旗舰道场学术档案",
        "region": "美国",
        "languages": "zh,lzh,en",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },

    # === Tibetan: Drikung Kagyu ===
    {
        "code": "drikung-translation",
        "name_zh": "直贡噶举翻译资源",
        "name_en": "Drikung Kagyu Translation Resources",
        "base_url": "https://www.drikungtranslation.com/resources/",
        "description": "直贡噶举官方翻译组发布的资源库，含 Garchen Rinpoche 及历代直贡上师法本仪轨的 PDF/EPUB/pecha 藏英对照下载，填补藏传次主流支派资源空白",
        "region": "国际",
        "languages": "bo,en",
        "research_fields": "tibetan",
        "supports_search": False,
        "has_remote_fulltext": True,
    },

    # === Tibetan: Jonang (Tāranātha) ===
    {
        "code": "taranatha-works",
        "name_zh": "多罗那他全集（觉囊派）",
        "name_en": "Tāranātha's Collected Works",
        "base_url": "https://taranathascollectedworks.com/",
        "description": "觉囊派 Jetsun Tāranātha 23 卷 370 篇 Dzamthang 版完整著作目录与已译本索引（藏英对照），是觉囊派文献研究的入口站",
        "region": "国际",
        "languages": "bo,en",
        "research_fields": "tibetan",
        "supports_search": True,
        "has_remote_fulltext": False,
    },

    # === Theravada UK forest tradition ===
    {
        "code": "forest-sangha",
        "name_zh": "阿姜查英国传承法谈书库",
        "name_en": "Forest Sangha Publications",
        "base_url": "https://www.forestsangha.org/teachings",
        "description": "阿姜查传承（Amaravati / Cittaviveka 等英国寺院）官方电子书库，免费下载 Sumedho、Amaro、Pasanno 等森林禅西传第二代长老的法谈集与开示文集",
        "region": "英国",
        "languages": "en,pa",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
]


def upgrade() -> None:
    for s in SOURCES:
        name_en = f"'{s['name_en']}'" if s["name_en"] else "NULL"
        desc = s["description"].replace("'", "''")
        name_zh = s["name_zh"].replace("'", "''")
        supports_search = "true" if s.get("supports_search") else "false"
        has_remote_fulltext = "true" if s.get("has_remote_fulltext") else "false"
        op.execute(
            text(
                f"INSERT INTO data_sources "
                f"(code, name_zh, name_en, base_url, description, "
                f"access_type, region, languages, research_fields, "
                f"supports_search, has_remote_fulltext, "
                f"sort_order, is_active) "
                f"VALUES ('{s['code']}', '{name_zh}', {name_en}, '{s['base_url']}', "
                f"'{desc}', 'open', '{s['region']}', "
                f"'{s['languages']}', '{s['research_fields']}', "
                f"{supports_search}, {has_remote_fulltext}, "
                f"0, true) "
                f"ON CONFLICT (code) DO NOTHING"
            )
        )


def downgrade() -> None:
    codes = ", ".join(f"'{s['code']}'" for s in SOURCES)
    op.execute(text(f"DELETE FROM data_sources WHERE code IN ({codes})"))
