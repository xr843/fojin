"""Add 11 Buddhist canon / Tripitaka digital resource sites.

Covers Chinese, Japanese, and international canon platforms discovered
via web survey on 2026-03-06. All checked against existing sources for
duplicates — none overlap.

Revision ID: 0060
Revises: 0059
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

sources = sa.table(
    "data_sources",
    sa.column("code", sa.String),
    sa.column("name_zh", sa.String),
    sa.column("name_en", sa.String),
    sa.column("base_url", sa.String),
    sa.column("description", sa.Text),
    sa.column("region", sa.String),
    sa.column("languages", sa.String),
    sa.column("access_type", sa.String),
    sa.column("supports_search", sa.Boolean),
    sa.column("supports_fulltext", sa.Boolean),
    sa.column("supports_api", sa.Boolean),
    sa.column("is_active", sa.Boolean),
)

NEW_SOURCES = [
    {
        "code": "fgs-etext",
        "name_zh": "佛光山电子大藏经",
        "name_en": "Fo Guang Shan Electronic Tripitaka",
        "base_url": "https://etext.fgs.org.tw/",
        "description": "佛光大藏经十六藏电子全文在线阅读，含校勘、分段标点、名相释义及专论索引。",
        "region": "中国台湾",
        "languages": "lzh,zh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "deerpark-app",
        "name_zh": "汉文大藏经(Deerpark)",
        "name_en": "Deerpark Chinese Tripitaka Reader",
        "base_url": "https://deerpark.app/",
        "description": "优雅排版的汉文大藏经在线阅读平台，收录4,700+经文、2万卷，支持PDF下载与Kindle推送，数据源自CBETA。",
        "region": "国际",
        "languages": "lzh,zh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "hrfjw-dzj",
        "name_zh": "华人佛教网大藏经",
        "name_en": "Huaren Buddhist Network Tripitaka",
        "base_url": "https://www.hrfjw.com/dazangjing/",
        "description": "提供乾隆大藏经、大正藏等大藏经目录与全文在线阅读。",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "cbeta-tripitaka",
        "name_zh": "CBETA漢文大藏經(多版本浏览)",
        "name_en": "CBETA Chinese Tripitaka Multi-Canon Browser",
        "base_url": "https://tripitaka.cbeta.org/",
        "description": "CBETA多版本大藏经浏览界面，涵盖大正藏、续藏、高丽藏、嘉兴藏、正史佛教资料等多部藏经的经录与全文。",
        "region": "中国台湾",
        "languages": "lzh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "cter",
        "name_zh": "汉文佛教大藏经电子资源(CTER)",
        "name_en": "Chinese Tripitaka Electronic Resources",
        "base_url": "https://cter.info/",
        "description": "汇集高丽藏、嘉兴藏、永乐南北藏、洪武南藏等多部大藏经PDF影像资源，总计79.6GB、6,701份PDF文档。",
        "region": "中国大陆",
        "languages": "lzh",
        "access_type": "external",
        "supports_search": False,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "yuezang",
        "name_zh": "大众阅藏(藏经矩阵)",
        "name_en": "Yuezang Public Canon Reading (Canon Matrix)",
        "base_url": "https://www.yuezang.org/",
        "description": "藏经矩阵系统，以矩阵形式展示房山石经至CBETA等30余部历代汉文大藏经，收录5,644种文献，支持关键字检索与版本对比。",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "daizoshuppan",
        "name_zh": "大藏出版(南传大藏经)",
        "name_en": "Daizo Shuppan (Nanden Daizokyo)",
        "base_url": "https://www.daizoshuppan.jp/",
        "description": "日本大藏出版社，出版《南传大藏经》（巴利三藏日文译本）及《国訳一切経》等佛教经典丛书。",
        "region": "日本",
        "languages": "ja,pi",
        "access_type": "external",
        "supports_search": False,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "ndl-bukkyozensho",
        "name_zh": "国立国会图书馆·大日本仏教全書",
        "name_en": "NDL Digital Collection: Dai-Nippon Bukkyo Zensho",
        "base_url": "https://dl.ndl.go.jp/info:ndljp/pid/952822",
        "description": "日本国立国会图书馆数字典藏中的《大日本仏教全書》全161卷，收录日本佛教著述珍稀文献。高楠順次郎等1912年编纂。",
        "region": "日本",
        "languages": "ja,lzh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "qldzj",
        "name_zh": "乾隆大藏经在线(般若堂)",
        "name_en": "Qianlong Tripitaka Online (Bore Tang)",
        "base_url": "http://www.qldzj.net/",
        "description": "提供乾隆大藏经（龙藏）、嘉兴藏、大正藏等多部大藏经在线阅读，以及道藏（正统道藏）全文。",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "followcn-sutras",
        "name_zh": "Followcn佛经在线阅读",
        "name_en": "Followcn Buddhist Sutras Online",
        "base_url": "https://www.followcn.com/sutras/",
        "description": "大藏经在线阅读平台，提供分类浏览与全文阅读功能。",
        "region": "中国大陆",
        "languages": "lzh,zh",
        "access_type": "external",
        "supports_search": True,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
    {
        "code": "cbeta-archive",
        "name_zh": "CBETA大藏经下载(大陆档案站)",
        "name_en": "CBETA Tripitaka Archive (Mainland Mirror)",
        "base_url": "https://archive.cbetaonline.cn/",
        "description": "CBETA大陆镜像离线下载站，提供多种格式（EPUB/PDF/HTML/XML）的大藏经数据包下载。",
        "region": "中国大陆",
        "languages": "lzh",
        "access_type": "external",
        "supports_search": False,
        "supports_fulltext": False,
        "supports_api": False,
        "is_active": True,
    },
]


def upgrade() -> None:
    for s in NEW_SOURCES:
        op.execute(
            sources.insert().values(**s)
        )


def downgrade() -> None:
    codes = [s["code"] for s in NEW_SOURCES]
    op.execute(
        sources.delete().where(sources.c.code.in_(codes))
    )
