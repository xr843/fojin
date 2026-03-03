"""seed 11 new data sources

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES = [
    {
        "code": "gretil",
        "name_zh": "GRETIL 梵文文献库",
        "name_en": "Göttingen Register of Electronic Texts in Indian Languages",
        "base_url": "https://gretil.sub.uni-goettingen.de",
        "description": "哥廷根大学印度语言电子文本登记册，收录大量梵文佛教文献",
    },
    {
        "code": "dsbc",
        "name_zh": "数字梵文佛典",
        "name_en": "Digital Sanskrit Buddhist Canon",
        "base_url": "https://www.dsbcproject.org",
        "description": "由Nagarjuna Institute维护的数字梵文佛教典藏",
    },
    {
        "code": "sat",
        "name_zh": "SAT 大正藏数据库",
        "name_en": "SAT Daizōkyō Text Database",
        "base_url": "https://21dzk.l.u-tokyo.ac.jp/SAT",
        "api_url": "https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php",
        "description": "东京大学大正新脩大藏经文本数据库，提供页面影像和文本对照",
    },
    {
        "code": "84000",
        "name_zh": "84000 藏传佛典翻译",
        "name_en": "84000: Translating the Words of the Buddha",
        "base_url": "https://read.84000.co",
        "api_url": "https://read.84000.co/translation",
        "description": "致力于将藏传佛教大藏经翻译为现代语言的国际非营利项目",
    },
    {
        "code": "ddb",
        "name_zh": "电子佛学辞典",
        "name_en": "Digital Dictionary of Buddhism",
        "base_url": "http://www.buddhism-dict.net/ddb",
        "description": "Charles Muller主编的佛学术语辞典，涵盖东亚佛学概念",
    },
    {
        "code": "ktk",
        "name_zh": "高丽大藏经",
        "name_en": "Koreana Tripitaka (Palman Daejanggyeong)",
        "base_url": "https://kb.nl.go.kr",
        "description": "韩国国家图书馆数字化的高丽大藏经影像与元数据",
    },
    {
        "code": "polyglotta",
        "name_zh": "多语种佛典图书馆",
        "name_en": "Bibliotheca Polyglotta",
        "base_url": "https://www2.hf.uio.no/polyglotta",
        "description": "奥斯陆大学多语种平行文本，含佛教经典多语对照",
    },
    {
        "code": "gandhari",
        "name_zh": "犍陀罗语佛典",
        "name_en": "Gandhari.org",
        "base_url": "https://gandhari.org",
        "description": "犍陀罗语（古代印度西北地区语言）佛教文献和铭文数据库",
    },
    {
        "code": "vri",
        "name_zh": "VRI 巴利三藏",
        "name_en": "Vipassana Research Institute Tipitaka",
        "base_url": "https://tipitaka.org",
        "description": "内观研究院发布的第六次结集巴利三藏，缅甸传统版本",
    },
    {
        "code": "dila",
        "name_zh": "DILA 权威数据库",
        "name_en": "Dharma Drum Institute of Liberal Arts Authority Database",
        "base_url": "https://authority.dila.edu.tw",
        "api_url": "https://authority.dila.edu.tw/api",
        "description": "法鼓文理学院佛学权威数据库，提供人名、地名、时代等规范数据",
    },
    {
        "code": "budsir",
        "name_zh": "泰国巴利三藏",
        "name_en": "Budsir Thai Pali Canon",
        "base_url": "https://budsir.mahidol.ac.th",
        "description": "泰国Mahidol大学维护的巴利三藏电子版",
    },
]


def upgrade() -> None:
    from sqlalchemy import text as sa_text

    conn = op.get_bind()
    for src in SOURCES:
        conn.execute(
            sa_text("""
                INSERT INTO data_sources (code, name_zh, name_en, base_url, api_url, description)
                VALUES (:code, :name_zh, :name_en, :base_url, :api_url, :description)
                ON CONFLICT (code) DO UPDATE SET
                    name_zh = EXCLUDED.name_zh,
                    name_en = EXCLUDED.name_en,
                    base_url = EXCLUDED.base_url,
                    api_url = EXCLUDED.api_url,
                    description = EXCLUDED.description
            """),
            {
                "code": src["code"],
                "name_zh": src["name_zh"],
                "name_en": src["name_en"],
                "base_url": src.get("base_url"),
                "api_url": src.get("api_url"),
                "description": src.get("description"),
            },
        )


def downgrade() -> None:
    from sqlalchemy import text as sa_text

    conn = op.get_bind()
    codes = [s["code"] for s in SOURCES]
    conn.execute(
        sa_text("DELETE FROM data_sources WHERE code = ANY(:codes)"),
        {"codes": codes},
    )
