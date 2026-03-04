"""add 15 new Buddhist digital sources (Tier 1 + Tier 2)

Web search audit (2026-03-04) discovered these missing sources:

TIER 1 — high priority (6):
1. dunhuang-cave17: 数字藏经洞 — 敦煌研究院3D数字重建
2. reiwa-daizokyo: 令和大蔵経 — 東京大学令和新修大蔵経
3. lanna-manuscripts: 兰纳数字写本库 — CrossAsia东南亚写本
4. siddham: SIDDHAM 梵文佛典语料库 — 台湾大学SIDDHAM
5. gandhari-sydney: 悉尼大学犍陀罗写本 — 犍陀罗写本数字化
6. bdrc-khmer: BDRC 高棉写本数字化 — 柬埔寨贝叶经数字化

TIER 2 — medium priority (9):
7. guji-cn: 国家古籍数字化资源总平台 — 中国国家古籍数字化
8. chinese-inscription: 中华石刻数据库 — 石刻佛教铭文
9. deerpark-ai: DeerPark AI 佛学问答 — AI佛学语义搜索
10. xueheng: 学衡数据平台 — 数字人文佛学数据
11. foxue-dictionary: 佛学大辞典在线 — 丁福保佛学大辞典
12. brill-buddhism: Brill 佛教百科 — 学术佛学参考
13. dharma-epigraphy: DHARMA 铭文项目 — 东南亚佛教铭文
14. gyan-bharatam: Gyan Bharatam 印度学文献 — 印度古典文献
15. bird-bukkyo: 佛教大学 BIRD — 日本佛教学术数据库

Revision ID: 0045
Revises: 0044
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (code, name_zh, name_en, base_url, region, languages,
#  has_remote_fulltext, supports_search, description)
NEW_SOURCES = [
    # ── Tier 1 ──
    ("dunhuang-cave17",
     "数字藏经洞",
     "Digital Cave Library (Cave 17)",
     "https://cave17.e-dunhuang.com/",
     "中国大陆", "lzh",
     False, False,
     "敦煌研究院与腾讯联合打造的藏经洞3D数字重建与文献浏览平台"),
    ("reiwa-daizokyo",
     "令和大蔵経",
     "Reiwa Shinshū Daizōkyō",
     "https://reiwadzk.dhii.asia/",
     "日本", "lzh,ja",
     True, True,
     "東京大学令和新修大蔵経テキストデータベース，高精度数字化大正藏全文"),
    ("lanna-manuscripts",
     "兰纳数字写本库",
     "Lanna Digital Manuscripts",
     "https://iiif.crossasia.org/s/lanna/",
     "德国", "pi,th",
     False, False,
     "CrossAsia平台兰纳（北泰）佛教写本数字化项目，IIIF影像浏览"),
    ("siddham",
     "SIDDHAM 梵文佛典语料库",
     "SIDDHAM Sanskrit Buddhist Corpus",
     "https://siddham.network/",
     "中国台湾", "sa,lzh",
     True, True,
     "台湾大学SIDDHAM梵文佛典数字语料库，梵汉对照与语法标注"),
    ("gandhari-sydney",
     "悉尼大学犍陀罗写本",
     "Sydney Gandhāran Manuscript Project",
     "https://gandhari-texts.sydney.edu.au/",
     "澳大利亚", "pgd",
     True, False,
     "悉尼大学犍陀罗语写本数字化与转录项目"),
    ("bdrc-khmer",
     "BDRC 高棉写本数字化",
     "BDRC Khmer Manuscript Digitization",
     "https://khmer-manuscripts.bdrc.io/",
     "柬埔寨", "km,pi",
     False, False,
     "佛教数字资源中心BDRC柬埔寨贝叶经写本数字化保护项目"),

    # ── Tier 2 ──
    ("guji-cn",
     "国家古籍数字化资源总平台",
     "National Digital Library of Ancient Texts",
     "https://www.guji.cn/",
     "中国大陆", "lzh,zh",
     True, True,
     "中国国家古籍保护中心古籍数字化资源总平台，含佛教典籍专题"),
    ("chinese-inscription",
     "中华石刻数据库",
     "Chinese Inscription Database",
     "https://inscription.ancientbooks.cn/",
     "中国大陆", "lzh",
     False, True,
     "中华石刻数据库，含大量佛教造像记、经幢、碑刻铭文"),
    ("deerpark-ai",
     "DeerPark AI 佛学问答",
     "DeerPark AI Buddhist Q&A",
     "https://deerpark.ai/",
     "美国", "en,lzh",
     False, True,
     "基于大语言模型的佛学语义搜索与问答平台"),
    ("xueheng",
     "学衡数据平台",
     "Xueheng Digital Humanities",
     "https://www.xueheng.net/",
     "中国大陆", "lzh,zh",
     False, True,
     "南京大学学衡数字人文平台，含佛学文献结构化数据与可视化"),
    ("foxue-dictionary",
     "佛学大辞典在线",
     "Foxue Dictionary Online",
     "https://foxue.bmcx.com/",
     "中国大陆", "lzh,zh",
     False, True,
     "丁福保《佛学大辞典》在线版，常用佛学术语查询工具"),
    ("brill-buddhism",
     "Brill 佛教百科",
     "Brill Encyclopedia of Buddhism",
     "https://referenceworks.brill.com/display/db/eob",
     "荷兰", "en",
     True, True,
     "Brill出版社佛教百科全书，权威英文佛学参考工具书"),
    ("dharma-epigraphy",
     "DHARMA 铭文项目",
     "DHARMA Epigraphy Project",
     "https://erc-dharma.github.io/",
     "法国", "sa,km,jv",
     True, False,
     "欧洲研究理事会DHARMA项目，南亚与东南亚佛教铭文数字化与研究"),
    ("gyan-bharatam",
     "Gyan Bharatam 印度学文献",
     "Gyan Bharatam Digital Library",
     "https://www.gyanbharatam.com/",
     "印度", "sa,hi",
     True, True,
     "印度古典文献数字图书馆，含梵文佛教写本与文献"),
    ("bird-bukkyo",
     "佛教大学 BIRD",
     "Bukkyō University BIRD Database",
     "https://bird.bukkyo-u.ac.jp/",
     "日本", "ja,lzh",
     False, True,
     "佛教大学综合佛教研究信息数据库（BIRD），日本佛教学术论文与资料检索"),
]


def upgrade() -> None:
    for rec in NEW_SOURCES:
        (code, name_zh, name_en, base_url, region, languages,
         has_remote, supports_search, description) = rec
        name_zh_e = name_zh.replace("'", "''")
        name_en_e = name_en.replace("'", "''")
        desc_e = description.replace("'", "''")
        op.execute(
            f"INSERT INTO data_sources "
            f"(code, name_zh, name_en, base_url, region, languages, "
            f"is_active, has_local_fulltext, has_remote_fulltext, "
            f"supports_search, supports_iiif, supports_api, "
            f"access_type, description) "
            f"VALUES ('{code}', '{name_zh_e}', '{name_en_e}', '{base_url}', "
            f"'{region}', '{languages}', "
            f"true, false, {has_remote}, "
            f"{supports_search}, false, false, "
            f"'external', '{desc_e}')"
        )


def downgrade() -> None:
    codes = [rec[0] for rec in NEW_SOURCES]
    del_str = ", ".join(f"'{c}'" for c in codes)
    op.execute(f"DELETE FROM data_sources WHERE code IN ({del_str})")
