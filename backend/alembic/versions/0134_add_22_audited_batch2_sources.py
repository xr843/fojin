"""Add 22 content-verified data sources (2026-05-15 全网检索 batch 2).

This is the follow-up to 0133. Batch 2 started from the 62 value-4/value-3
candidates and the 9 hosts that 0133's liveness probe could not reach.

Each of the 62 was opened and judged by a content-value rubric, not by
reputation: a candidate qualifies only if the site itself serves accessible
Buddhist material — full-text scripture, manuscript images/IIIF, a searchable
text/catalog database, downloadable scholarship, or structured datasets. Pure
institutional / temple homepages, brochure or tourist pages, and dead or
hijacked domains were rejected. 37 of 62 failed that bar (most were Japanese
sect temple homepages with visit info but no texts; two domains had been
taken over by unrelated spam sites).

25 passed the content check; a dedup pass over the full migration history
then dropped 3 already-catalogued sources (dhammatalks = existing
'dhammatalks', jodo.or.jp = existing 'jodo-shu', icabs.ac.jp main site —
its two databases are already in as 'icabs-koshakyo'/'icabs-nara-chokujo').

So this migration imports the remaining 22. Several use a corrected base_url
pointing at the actual content sub-site rather than the institutional front
page (sac-manuscripts, utsbm-tokyo, asianart-sf, va-museum,
indica-buddhica-repo).

access_type='external'; sort_order 0; is_active true;
INSERT ... ON CONFLICT (code) DO NOTHING for idempotency.

Revision ID: 0134
Revises: 0133
Create Date: 2026-05-15
"""

from alembic import op
from sqlalchemy import text

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None


NEW_SOURCES = [
    # ---- 藏传 ----
    {
        "code": "drikung-texts",
        "name_zh": "直贡噶举官方教法文献",
        "name_en": "Drikung Kagyu Order — Official Teaching Texts",
        "base_url": "https://drikung.org/texts/",
        "description": "直贡噶举派官方机构的教法文献区，提供多部可直接下载的传承教法 PDF——含帕摩竹巴传记、嘉察仁波切大手印教法、衮秋嘉灿多部哲学著作及历年冬季教法集，采开放许可（署名/非商用）。",
        "region": "印度",
        "languages": "bo,en",
        "research_fields": "tibetan",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    {
        "code": "garchen",
        "name_zh": "嘉察佛教学院",
        "name_en": "Garchen Buddhist Institute",
        "base_url": "https://garchen.net/",
        "description": "西方最大的直贡噶举道场，嘉察仁波切官方教法档案站，提供视频教法库、纪录片、越南语文本区及在线法本资源入口。",
        "region": "美国",
        "languages": "bo,en",
        "research_fields": "tibetan",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    # ---- 南传 / 东南亚 ----
    {
        "code": "paauk-ebooks",
        "name_zh": "帕奥森林禅林电子书库",
        "name_en": "Pa-Auk Forest Monastery — eBooks",
        "base_url": "https://www.paaukforestmonastery.org/ebooks",
        "description": "帕奥禅师止观体系的官方电子书库，收录《如实知见》《业的运作》《帕奥禅修手册》等十余部著作，均为可直接下载的 PDF。",
        "region": "缅甸",
        "languages": "en,my,pi",
        "research_fields": "theravada",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    {
        "code": "femc-khmer",
        "name_zh": "柬埔寨写本编辑基金会（FEMC）",
        "name_en": "Fonds pour l'Édition des Manuscrits du Cambodge",
        "base_url": "https://femc.huma-num.fr/",
        "description": "法国远东学院（EFEO）主持的柬埔寨贝叶写本数字化项目，2024 年上线 Heurist 平台，提供柬埔寨佛教写本的完整影像与元数据清单，影像存于 Nakala 仓库，可检索浏览。",
        "region": "柬埔寨",
        "languages": "km,pi,fr",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "aimwell",
        "name_zh": "Aimwell 巴利文献库",
        "name_en": "Aimwell",
        "base_url": "https://www.aimwell.org/",
        "description": "由 Bhikkhu Pesala 维护的巴利文献库，收录马哈希等缅甸禅师著作的 HTML 与 PDF 校订本、巴利专有名词词典（DPPN）及巴利语学习资源，全站可打包下载。",
        "region": "英国",
        "languages": "pi,en",
        "research_fields": "theravada,dictionary",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    {
        "code": "sac-manuscripts",
        "name_zh": "泰国写本数据库（诗琳通人类学中心）",
        "name_en": "Manuscripts of Thailand — SAC",
        "base_url": "https://manuscripts.sac.or.th/",
        "description": "泰国诗琳通人类学中心（SAC）的「泰国写本」数据库，约 1800 条写本记录，含数字影像、编目与主题标签，可检索浏览，涵盖巴利贝叶与泰文古经卷。",
        "region": "泰国",
        "languages": "th,pi",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "hoavouu",
        "name_zh": "慈悲花佛教图书馆（Hoa Vô Ưu）",
        "name_en": "Hoa Vô Ưu Buddhist Library",
        "base_url": "https://hoavouu.com/",
        "description": "越南语佛教数字图书馆，提供佛经全文（法句经、楞严经等）、释清慈讲座文集、有声经典与译著，可在线阅读，是越南最大的佛教文献站之一。",
        "region": "越南",
        "languages": "vi",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "daophatkhatsi",
        "name_zh": "越南乞士派佛教",
        "name_en": "Đạo Phật Khất Sĩ — Vietnamese Mendicant Tradition",
        "base_url": "https://daophatkhatsi.vn/",
        "description": "越南本土独有的「乞士派」（Khất Sĩ）佛教官方文献站，提供经与偈颂、明灯祖师《真理》（Chơn Lý）教义全文、三藏研究、译著及《莲炬》期刊等可读文本。",
        "region": "越南",
        "languages": "vi",
        "research_fields": "han",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    {
        "code": "eap791-lanten",
        "name_zh": "老挝蓝靛瑶文献遗产数字库（EAP791）",
        "name_en": "Digital Library of the Lanten Textual Heritage",
        "base_url": "https://eap.bl.uk/project/EAP791",
        "description": "大英图书馆濒危档案计划（EAP）数字化的老挝蓝靛瑶（Lanten）族宗教写本，已完成 768 部写本影像，含汉字书写的仪轨与佛道混合文献，藏品页可在线浏览。",
        "region": "老挝",
        "languages": "lo,zh",
        "research_fields": "han",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "ia-sixth-council",
        "name_zh": "第六结集巴利三藏（Internet Archive）",
        "name_en": "Sixth Council Tipiṭaka — Internet Archive",
        "base_url": "https://archive.org/details/03-vin-03",
        "description": "Internet Archive 上的第六结集罗马转写巴利三藏公有领域副本，提供 PDF/EPUB/全文 OCR/JP2 影像多种格式，可下载并全文检索，是不依赖 tipitaka.org 的长期保存镜像。",
        "region": "国际",
        "languages": "pi",
        "research_fields": "theravada",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    # ---- 日本 / 韩国 ----
    {
        "code": "encykorea",
        "name_zh": "韩国民族文化大百科全书",
        "name_en": "Encyclopedia of Korean Culture",
        "base_url": "https://encykorea.aks.ac.kr/",
        "description": "韩国学中央研究院（AKS）编纂的可检索全文百科数据库，覆盖十三大领域、宗教哲学类逾一万二千条，含韩国佛教人物、寺院、宗派与概念的权威词条，条目可在线阅读全文。",
        "region": "韩国",
        "languages": "ko,lzh",
        "research_fields": "han,dictionary",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "otani-repo",
        "name_zh": "大谷大学学术机构库",
        "name_en": "Otani University Repository",
        "base_url": "https://otani.repo.nii.ac.jp/",
        "description": "大谷大学（真宗大谷派）的学术机构库，收录《大谷學報》等学术纪要与博士论文，记录页含 PDF 全文下载，可检索，是真宗学研究的重要文献来源。",
        "region": "日本",
        "languages": "ja,lzh",
        "research_fields": "han,dh",
        "supports_search": True,
        "has_remote_fulltext": True,
    },
    {
        "code": "sotozen-global",
        "name_zh": "曹洞宗国际中心",
        "name_en": "Sōtō Zen Buddhism International Center",
        "base_url": "https://global.sotozen.com/",
        "description": "曹洞宗面向国际的官方门户，含 Library 板块：逐月发布的《正法眼藏》英译 PDF、《传光录》、Soto Zen Journal 及般若心经/观音经等日课经文译文，提供可读可下载的宗派典籍。",
        "region": "日本",
        "languages": "en,ja",
        "research_fields": "han",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    # ---- 梵学 / 西方学术 / 博物馆 ----
    {
        "code": "cleveland-art-api",
        "name_zh": "克利夫兰艺术博物馆开放数据",
        "name_en": "Cleveland Museum of Art — Open Access",
        "base_url": "https://openaccess-api.clevelandart.org/",
        "description": "克利夫兰艺术博物馆的开放数据计划，以 CC0 协议与 RESTful API 提供逾六万四千件藏品的 JSON/CSV 数据（每日更新，无需密钥），含佛教绘画与造像，可程序化检索，GitHub 同步全量数据集。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "harvard-art-api",
        "name_zh": "哈佛艺术博物馆 API",
        "name_en": "Harvard Art Museums API",
        "base_url": "https://www.harvardartmuseums.org/collections/api",
        "description": "哈佛艺术博物馆的开放 API，提供艺术品、照片与档案的 JSON 元数据（每日刷新，免费密钥），亚洲艺术藏品含佛教文物，可检索 “Buddhist” 关键词，附完整 GitHub 文档。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "jocbs",
        "name_zh": "牛津佛学研究中心学刊",
        "name_en": "Journal of the Oxford Centre for Buddhist Studies",
        "base_url": "https://jocbs.org/",
        "description": "牛津佛学研究中心的正式学术期刊，已出版二十五卷，按卷期组织，支持作者/标题/摘要/全文检索，由 Gombrich、Wynne 等学者主编。",
        "region": "英国",
        "languages": "en",
        "research_fields": "theravada,tibetan,han",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "buddhist-studies-review",
        "name_zh": "佛教研究评论",
        "name_en": "Buddhist Studies Review",
        "base_url": "https://journal.equinoxpub.com/BSR",
        "description": "英国佛教学协会（UKABS）官方期刊，由 Equinox 出版，为欧洲佛教学界的核心刊物；近年卷期为订阅制，早期卷次开放获取，可下载论文 PDF。",
        "region": "英国",
        "languages": "en",
        "research_fields": "theravada,tibetan,han",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "utsbm-tokyo",
        "name_zh": "东京大学图书馆梵语佛典写本数据库",
        "name_en": "Sanskrit Buddhist Manuscripts in the University of Tokyo Library",
        "base_url": "https://dzkimgs.l.u-tokyo.ac.jp/ut_skt_manuscripts/",
        "description": "东京大学印度哲学佛教学研究室维护的梵语佛典写本数据库，以高质量 IIIF 影像呈现河口慧海-高楠顺次郎收集的梵语写本，是瑜伽行派系写本研究的专题库。",
        "region": "日本",
        "languages": "sa,en",
        "research_fields": "sanskrit",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "asianart-sf",
        "name_zh": "旧金山亚洲艺术博物馆藏品库",
        "name_en": "Asian Art Museum of San Francisco — Collections",
        "base_url": "https://collections.asianart.org/",
        "description": "旧金山亚洲艺术博物馆的在线藏品库，逾一万八千件在线对象，喜马拉雅、中国与南亚部分的佛教内容极为丰富（含纪年最早的中国佛像之一），可检索浏览。",
        "region": "美国",
        "languages": "en",
        "research_fields": "art",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "va-museum",
        "name_zh": "维多利亚与阿尔伯特博物馆藏品库",
        "name_en": "Victoria and Albert Museum — Collections",
        "base_url": "https://collections.vam.ac.uk/",
        "description": "英国 V&A 博物馆的在线藏品库，逾一百二十五万件对象，支持标题/类型/材质/产地/年代多字段检索，含南亚、中国与日本的佛教文物及犍陀罗造像。",
        "region": "英国",
        "languages": "en",
        "research_fields": "art",
        "supports_search": True,
        "has_remote_fulltext": False,
    },
    {
        "code": "glorisun-pub",
        "name_zh": "旭日全球佛教研究网络出版物",
        "name_en": "Glorisun Global Network Publications",
        "base_url": "https://glorisunglobalnetwork.org/publications/",
        "description": "旭日全球佛教研究网络的出版物专栏，含开放获取的佛教学术专著与会议论文集，与《华林国际佛教学刊》同源，2024-2026 持续更新。",
        "region": "国际",
        "languages": "en,lzh",
        "research_fields": "han,dh",
        "supports_search": False,
        "has_remote_fulltext": True,
    },
    {
        "code": "indica-buddhica-repo",
        "name_zh": "Indica et Buddhica 文库",
        "name_en": "Indica et Buddhica Repositorium",
        "base_url": "https://www.indica-et-buddhica.com/repositorium",
        "description": "Indica et Buddhica 的数字文本库，收录龙树《中论》等梵文文本、寂天《入菩萨行论》数字版、SARIT TEI 文本、Āśā Archives 写本目录及梵藏汉术语词典，是可访问的佛学数字文本与工具集。",
        "region": "新西兰",
        "languages": "sa,bo,lzh,en",
        "research_fields": "sanskrit,dh",
        "supports_search": True,
        "has_remote_fulltext": True,
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
