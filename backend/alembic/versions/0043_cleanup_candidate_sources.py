"""cleanup candidate sources: activate 4, delete 33 useless placeholders

Audit of 76 inactive candidate sources (2026-03-04):

ACTIVATE (4) — confirmed operational with Buddhist digital resources:
- chung-hwa: 中华佛学研究所 (chibs.edu.tw) — active digital library
- jodo-shu: 净土宗综合研究所 — URL corrected to jodoshuzensho.jp
- dongguk-univ: 东国大学佛教学术院 — URL corrected to kabc.dongguk.edu
- sbb-asian: 柏林国家图书馆亚洲部 — Digital Turfan Archive

DELETE (33) — generic university homepages, placeholders, duplicates:
  28 generic university/institution homepages with no Buddhist digital resources
  + nagarjuna-inst (duplicate of dsbc), lotus-sutra (no URL placeholder),
    pune-bori (wrong URL), iiif-buddhist (protocol consortium, not data source),
    daizokyo-society (generic u-tokyo page)

Revision ID: 0043
Revises: 0042
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sources to activate
ACTIVATE_CODES = ["chung-hwa", "jodo-shu", "dongguk-univ", "sbb-asian"]

# URL corrections for activated sources
URL_FIXES = {
    "jodo-shu": "http://jodoshuzensho.jp/",
    "dongguk-univ": "https://kabc.dongguk.edu/",
}

# Sources to delete — generic homepages, placeholders, duplicates
DELETE_CODES = [
    "anu-buddhism",        # generic uni homepage
    "barcelona-buddhism",  # generic uni homepage
    "bhu-sanskrit",        # generic uni homepage
    "chula-pali",          # generic uni homepage
    "daizokyo-society",    # generic u-tokyo page
    "fudan-buddhism",      # generic uni homepage
    "ghent-buddhism",      # generic uni homepage
    "goettingen-sanskrit", # generic uni homepage
    "harvard-buddhism",    # generic uni homepage
    "iiif-buddhist",       # protocol consortium, not a data source
    "kelaniya-univ",       # generic uni homepage
    "leiden-univ",         # generic uni homepage
    "lmu-buddhism",        # generic uni homepage
    "lotus-sutra",         # no URL, placeholder
    "mcgill-buddhism",     # generic uni homepage
    "melbourne-chinese",   # generic uni homepage
    "michigan-buddhism",   # generic uni homepage
    "nagarjuna-inst",      # duplicate of dsbc
    "nanjing-univ",        # generic uni homepage
    "pku-buddhism",        # generic uni homepage
    "pune-bori",           # wrong URL
    "renmin-buddhism",     # generic uni homepage
    "shandong-univ",       # generic uni homepage
    "sydney-buddhism",     # generic uni homepage
    "toronto-buddhism",    # generic uni homepage
    "tsinghua-dh",         # generic uni homepage
    "turin-tibetan",       # generic uni homepage
    "ubc-buddhism",        # generic uni homepage
    "ucla-buddhism",       # generic uni homepage
    "virginia-buddhism",   # generic uni homepage
    "wisconsin-buddhism",  # generic uni homepage
    "wuhan-univ",          # generic uni homepage
    "zju-buddhism",        # generic uni homepage
]

# For downgrade: store deleted records so they can be re-inserted
# (name_zh, code, base_url, region, is_active)
DELETED_RECORDS = [
    ("澳大利亚国立大学佛学", "anu-buddhism", "https://www.anu.edu.au/", "澳大利亚"),
    ("巴塞罗那自治大学东亚佛学", "barcelona-buddhism", "https://www.uab.cat/", "西班牙"),
    ("贝纳勒斯印度大学梵文系", "bhu-sanskrit", "https://www.bhu.ac.in/", "印度"),
    ("朱拉隆功大学巴利佛学", "chula-pali", "https://www.chula.ac.th/", "泰国"),
    ("大藏经学术用语研究会", "daizokyo-society", "https://www.l.u-tokyo.ac.jp/", "日本"),
    ("复旦大学佛学研究中心", "fudan-buddhism", "https://www.fudan.edu.cn/", "中国大陆"),
    ("根特大学东方语言佛学", "ghent-buddhism", "https://www.ugent.be/", "比利时"),
    ("哥廷根大学梵文学", "goettingen-sanskrit", "https://www.uni-goettingen.de/", "德国"),
    ("哈佛大学南亚佛学研究", "harvard-buddhism", "https://www.harvard.edu/", "美国"),
    ("IIIF 佛教写本联盟", "iiif-buddhist", "https://iiif.io/", "国际"),
    ("凯拉尼亚大学巴利佛学", "kelaniya-univ", "https://www.kln.ac.lk/", "斯里兰卡"),
    ("莱顿大学佛学研究所", "leiden-univ", "https://www.universiteitleiden.nl/", "荷兰"),
    ("慕尼黑大学印度学与藏学", "lmu-buddhism", "https://www.lmu.de/", "德国"),
    ("法华经多语种数据库", "lotus-sutra", None, "国际"),
    ("麦吉尔大学佛教研究", "mcgill-buddhism", "https://www.mcgill.ca/", "加拿大"),
    ("墨尔本大学中国古代文学典籍", "melbourne-chinese", "https://www.unimelb.edu.au/", "澳大利亚"),
    ("密歇根大学佛学研究", "michigan-buddhism", "https://lsa.umich.edu/", "美国"),
    ("龙树学院(DSBC)", "nagarjuna-inst", "https://www.dsbcproject.org/", "印度"),
    ("南京大学域外汉籍研究所", "nanjing-univ", "https://www.nju.edu.cn/", "中国大陆"),
    ("北京大学佛教典籍与艺术研究中心", "pku-buddhism", "https://www.pku.edu.cn/", "中国大陆"),
    ("浦那东方学研究所", "pune-bori", "https://www.bfrInstitute.org/", "印度"),
    ("中国人民大学佛教与宗教学研究所", "renmin-buddhism", "https://www.ruc.edu.cn/", "中国大陆"),
    ("山东大学佛学研究中心", "shandong-univ", "https://www.sdu.edu.cn/", "中国大陆"),
    ("悉尼大学佛学与道学研究", "sydney-buddhism", "https://www.sydney.edu.au/", "澳大利亚"),
    ("多伦多大学佛学研究", "toronto-buddhism", "https://www.utoronto.ca/", "加拿大"),
    ("清华大学数字人文中心", "tsinghua-dh", "https://www.tsinghua.edu.cn/", "中国大陆"),
    ("都灵大学藏学研究", "turin-tibetan", "https://www.unito.it/", "意大利"),
    ("不列颠哥伦比亚大学佛学", "ubc-buddhism", "https://www.ubc.ca/", "加拿大"),
    ("加州大学洛杉矶分校佛学", "ucla-buddhism", "https://www.ucla.edu/", "美国"),
    ("弗吉尼亚大学藏传佛教资源", "virginia-buddhism", "https://www.virginia.edu/", "美国"),
    ("威斯康辛大学佛教研究", "wisconsin-buddhism", "https://www.wisc.edu/", "美国"),
    ("武汉大学古籍研究所", "wuhan-univ", "https://www.whu.edu.cn/", "中国大陆"),
    ("浙江大学佛教文献研究中心", "zju-buddhism", "https://www.zju.edu.cn/", "中国大陆"),
]


def upgrade() -> None:
    # 1. Activate 4 sources
    codes_str = ", ".join(f"'{c}'" for c in ACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = true "
        f"WHERE code IN ({codes_str})"
    )

    # 2. Fix URLs
    for code, url in URL_FIXES.items():
        op.execute(
            f"UPDATE data_sources SET base_url = '{url}' "
            f"WHERE code = '{code}'"
        )

    # 3. Delete 33 useless placeholder sources
    del_str = ", ".join(f"'{c}'" for c in DELETE_CODES)
    op.execute(f"DELETE FROM data_sources WHERE code IN ({del_str})")


def downgrade() -> None:
    # 1. Re-insert deleted sources
    for name_zh, code, base_url, region in DELETED_RECORDS:
        url_val = f"'{base_url}'" if base_url else "NULL"
        op.execute(
            f"INSERT INTO data_sources (name_zh, code, base_url, region, is_active) "
            f"VALUES ('{name_zh}', '{code}', {url_val}, '{region}', false)"
        )

    # 2. Restore original URLs
    op.execute(
        "UPDATE data_sources SET base_url = 'https://www.jodo.or.jp/' "
        "WHERE code = 'jodo-shu'"
    )
    op.execute(
        "UPDATE data_sources SET base_url = 'https://www.dongguk.edu/' "
        "WHERE code = 'dongguk-univ'"
    )

    # 3. Deactivate the 4 sources
    codes_str = ", ".join(f"'{c}'" for c in ACTIVATE_CODES)
    op.execute(
        f"UPDATE data_sources SET is_active = false "
        f"WHERE code IN ({codes_str})"
    )
