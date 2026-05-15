"""Add 17 audited high-value data sources (2026-05-15 全网检索 batch 1).

Discovery: 4 parallel research agents swept four verticals — Tibetan/Vajrayāna,
Theravāda/SE-Asia, Japan/Korea East-Asian, Sanskrit/Western-academic — against
the live 547-source catalog, yielding 89 raw candidates.

Pre-import audit (the reason this batch is only 17, not 27):
  - Domain grep vs all 547 *active* base_urls caught 7 false positives that
    agents wrongly reported as "未收录" — incl. 4 exact-URL duplicates that
    were rated value-5 (rsbmpproject.org=rsbmp, tibetanlibrary.org=
    tibetanlibrary-ltwa, referenceworks.brill.com/.../enbo=brill-buddhism,
    www.bdk.or.jp=bdk-daizokyo) plus www.bnf.fr (=bnf-buddhism) and two
    www.bdrc.io pages that are a blog post / program page, not data sources.
  - HTTP liveness probe (browser-UA curl) flagged 9 hosts unreachable from
    our egress; 2 of them were value-5 (paaukforestmonastery.org/ebooks,
    femc.huma-num.fr) and are held back for a follow-up batch pending a
    manual browser check rather than guessed-in here.
  - Code review caught 3 more duplicates: the /api/sources catalog only
    returns *active* rows, so de-activated sources slipped the first grep.
    A second pass over every base_url in the full migration history dropped
    iriz-hanazono (= existing 'iriz-hanazono', seeded 0018, deactivated
    0046), nlab-bhutan (= existing 'bhutan-lib', library.gov.bt) and
    gandhara-lmu (= existing entry from 0022, same LMU Gandhāra project).

So this migration imports only the 17 value-5 candidates that are BOTH
confirmed-new (vs the full migration history, not just active rows) AND
confirmed-reachable. value-4/3 candidates and the 9 flagged hosts are
deliberately deferred.

access_type='external' to match the catalog's dominant pattern (437/547 rows)
and the existing journal entries (jbe-ethics, jiabs, jgb-global all 'external');
the /sources page is a navigation index, so these are external link targets.
sort_order 0; is_active true. INSERT ... ON CONFLICT (code) DO NOTHING keeps
the migration idempotent.

Revision ID: 0133
Revises: 0132
Create Date: 2026-05-15
"""

from alembic import op
from sqlalchemy import text

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


NEW_SOURCES = [
    # ---- 藏传 / 瓦杰拉雅那 ----
    {
        "code": "tmpv-vienna",
        "name_zh": "维也纳藏文写本计划（TMPV）",
        "name_en": "Tibetan Manuscript Project Vienna",
        "base_url": "https://tmpv.univie.ac.at/",
        "description": "维也纳大学主持的喜马拉雅藏文写本田野调查与编目项目，系统记录西藏西部及周边地区的甘珠尔/丹珠尔写本谱系，2017 年起持续产出，与已收录的 rKTs 经录数据库互补，为藏文大藏经版本学研究提供一手写本证据。",
        "region": "奥地利",
        "languages": "bo,en,sa",
        "research_fields": "tibetan,dh",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "wisdom-experience",
        "name_zh": "智慧典藏（Wisdom Experience）",
        "name_en": "Wisdom Experience",
        "base_url": "https://wisdomexperience.org/",
        "description": "Wisdom Publications 官方在线阅读与学习平台，提供《藏传佛教经典文库》（The Library of Tibetan Classics）等权威英译全文阅读，涵盖宗喀巴、隆钦巴等大师著作及配套课程，是西方藏传佛教经典翻译的核心出版方。",
        "region": "美国",
        "languages": "en,bo",
        "research_fields": "tibetan",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "tidl",
        "name_zh": "藏传国际数字图书馆（TIDL）",
        "name_en": "Tibetan International Digital Library",
        "base_url": "https://tidl.org/",
        "description": "由达赖喇嘛尊者办公室主持的跨机构藏文资源整合平台，聚合 400 余家收藏机构的文本与音视频资料，定位为全球藏文数字资源的发现与整合枢纽。",
        "region": "国际",
        "languages": "bo,en",
        "research_fields": "tibetan,dh",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "webuddhist",
        "name_zh": "WeBuddhist 多语经文平台",
        "name_en": "WeBuddhist",
        "base_url": "https://webuddhist.com/",
        "description": "OpenPecha、BDRC、Monlam 与伯克利等机构联合开发的多语佛典检索与平行对照平台，支持偈颂级（verse-level）跨语种查询与社区注释，2025 年进入公测，是 AI 时代藏文多语佛典基础设施的代表性项目。",
        "region": "国际",
        "languages": "bo,en,zh,pi,sa",
        "research_fields": "tibetan,dh",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    # ---- 南传 / 东南亚 ----
    {
        "code": "sajjhaya",
        "name_zh": "世界三藏沙加亚版（Tipiṭaka Sajjhāya）",
        "name_en": "World Tipiṭaka Sajjhāya Recitation Edition",
        "base_url": "https://www.sajjhaya.org/",
        "description": "泰国出版的当代权威巴利三藏校订版，以 80 册罗马拼音、泰文及音素注音三种形式呈现并附完整诵读录音，与 VRI/CST 第六结集版互补，是巴利圣典发音学与校勘研究的重要资源。",
        "region": "泰国",
        "languages": "pi,th",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "sitagu-library",
        "name_zh": "西达古佛教学院图书馆（曼德勒）",
        "name_en": "Sitagu Buddhist Academy Library, Mandalay",
        "base_url": "https://library.sbamdy.edu.mm/",
        "description": "缅甸最重要的佛教学术机构之一西达古佛教学院的在线馆藏检索系统，收录 6000 余种缅文书籍、巴利典籍及贝叶经编目，是缅甸上座部佛教学术文献的重要入口。",
        "region": "缅甸",
        "languages": "my,pi,en",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "tejaniya",
        "name_zh": "德加尼亚禅师教法库",
        "name_en": "Sayadaw U Tejaniya — Teachings Archive",
        "base_url": "https://tejaniyasayadaw.space/",
        "description": "缅甸当代著名禅师德加尼亚（Sayadaw U Tejaniya）的官方教法资源库，提供完整的在线教法文本、音频、视频及多部著作，系统呈现其以觉知心为核心的内观禅修方法。",
        "region": "缅甸",
        "languages": "en,my",
        "research_fields": "theravada",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    {
        "code": "bia-buddhadasa",
        "name_zh": "佛使比丘档案馆（解脱自在园）",
        "name_en": "Buddhadāsa Indapañño Archives",
        "base_url": "https://www.bia.or.th/",
        "description": "泰国 20 世纪最具影响力的改革派论师佛使比丘（Buddhadāsa Bhikkhu）的官方档案中心，收藏其全集著作、讲座音频及历史档案，是研究泰国现代佛教思想的核心机构。",
        "region": "泰国",
        "languages": "th,en,pi",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "langmai-tangkinh",
        "name_zh": "梅村越南文藏经阁",
        "name_en": "Plum Village — Vietnamese Sutra Repository (Làng Mai)",
        "base_url": "https://langmai.org/tang-kinh-cac/",
        "description": "一行禅师创立的梅村僧团越南文官方藏经阁，收录其越南文著作、开示与经典译注全集，内容独立于已收录的英文站 plumvillage.org，是越南禅传统现代教法的权威来源。",
        "region": "法国",
        "languages": "vi,fr",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    # ---- 日本 / 韩国 东亚 ----
    {
        "code": "jstage-ibk",
        "name_zh": "印度学佛教学研究（J-STAGE）",
        "name_en": "Journal of Indian and Buddhist Studies (J-STAGE)",
        "base_url": "https://www.jstage.jst.go.jp/browse/ibk",
        "description": "日本印度学佛教学会旗舰期刊《印度学佛教学研究》（1952 年至今）在 J-STAGE 平台的全文开放库，提供数万篇佛教学论文 PDF，是 INBUDS 索引之外日本佛教学术正文的主要来源。",
        "region": "日本",
        "languages": "ja,en,lzh",
        "research_fields": "han,dh",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "nanzan-jjrs",
        "name_zh": "日本宗教研究杂志（南山宗教文化研究所）",
        "name_en": "Japanese Journal of Religious Studies",
        "base_url": "https://nirc.nanzan-u.ac.jp/en/publications/jjrs/",
        "description": "南山宗教文化研究所出版的《日本宗教研究杂志》，全文开放，是英文学界研究日本佛教与神道的核心期刊。",
        "region": "日本",
        "languages": "en",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    # ---- 梵学 / 印度学手稿 ----
    {
        "code": "ngmcp-hamburg",
        "name_zh": "尼泊尔-德国写本编目项目（NGMCP）",
        "name_en": "Nepalese-German Manuscript Cataloguing Project",
        "base_url": "https://www.aai.uni-hamburg.de/en/forschung/ngmcp.html",
        "description": "汉堡大学主持的尼泊尔-德国写本编目项目门户，承接 NGMPP 拍摄的约 18 万件梵语、尼瓦尔语及藏文写本微缩胶卷的编目工作，是全球最大的尼泊尔佛教与印度教写本目录。",
        "region": "德国",
        "languages": "sa,ne,bo",
        "research_fields": "sanskrit",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "pacific-world",
        "name_zh": "太平洋世界（佛教研究学院期刊）",
        "name_en": "Pacific World — Journal of the Institute of Buddhist Studies",
        "base_url": "https://pwj.shin-ibs.edu/",
        "description": "美国佛教研究学院（Institute of Buddhist Studies, Shin-IBS）旗舰开放获取期刊，聚焦净土与现代佛教研究，全文免费开放。",
        "region": "美国",
        "languages": "en",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "hualin-journal",
        "name_zh": "华林国际佛教学刊",
        "name_en": "Hualin International Journal of Buddhist Studies",
        "base_url": "https://glorisunglobalnetwork.org/hualin-international-journal-of-buddhist-studies/",
        "description": "北京大学佛教研究中心与旭日全球佛教研究网络合办的中英双语开放获取学术期刊，聚焦东亚佛教研究，全文免费开放。",
        "region": "国际",
        "languages": "en,lzh",
        "research_fields": "han,dh",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "met-openaccess",
        "name_zh": "大都会艺术博物馆开放数据",
        "name_en": "The Metropolitan Museum of Art — Open Access",
        "base_url": "https://metmuseum.github.io/",
        "description": "纽约大都会艺术博物馆的开放数据计划，以 CC0 协议与 RESTful API 提供数十万件藏品元数据及 IIIF 图像，其中包含大量佛教雕塑、写经与造像，可作为佛教艺术维度的结构化数据源。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "si-asian-art-oa",
        "name_zh": "史密森尼国立亚洲艺术博物馆开放数据",
        "name_en": "Smithsonian National Museum of Asian Art — Open Access",
        "base_url": "https://asia-archive.si.edu/collections/smithsonian-open-access/",
        "description": "史密森尼国立亚洲艺术博物馆（原弗利尔-赛克勒美术馆）的开放数据计划，以 CC0 协议提供高分辨率亚洲艺术藏品图像，在高丽佛画与敦煌写经数字化方面成果突出。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art,dunhuang",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "rubin-museum",
        "name_zh": "鲁宾艺术博物馆（喜马拉雅艺术）",
        "name_en": "Rubin Museum of Himalayan Art",
        "base_url": "https://rubinmuseum.org/our-collection/",
        "description": "全球最大的喜马拉雅艺术专题博物馆，藏品涵盖 4000 余件藏传佛教与喜马拉雅地区艺术作品，2024 年起转向数字化与巡回展览模式，与 himalayanart.org 互补。",
        "region": "美国",
        "languages": "en,bo",
        "research_fields": "art,tibetan",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
]


def upgrade() -> None:
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
                f"        {q(s['base_url'])}, {q(s['description'])}, 'external', "
                f"        {q(s['region'])}, {q(s['languages'])}, {q(s['research_fields'])}, "
                f"        {supports_search}, {has_remote_fulltext}, "
                "         0, true) "
                "ON CONFLICT (code) DO NOTHING"
            )
        )


def downgrade() -> None:
    for s in NEW_SOURCES:
        op.execute(
            text(f"DELETE FROM data_sources WHERE code = '{s['code']}'")
        )
