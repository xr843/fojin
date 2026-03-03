"""add languages column to data_sources and backfill with Buddhist scripture languages

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Language codes (ISO 639-3) used in Buddhist studies ──
# lzh = Classical Chinese     sa  = Sanskrit           pi  = Pali
# bo  = Tibetan               pgd = Gandhari           kho = Khotanese
# sog = Sogdian               xto = Tocharian A        txb = Tocharian B
# oui = Old Uyghur            txg = Tangut             cmg = Classical Mongolian
# mnc = Manchu                th  = Thai               my  = Burmese
# si  = Sinhala               km  = Khmer              ja  = Japanese
# ko  = Korean                vi  = Vietnamese         en  = English
# de  = German                fr  = French

# Mapping: source_code -> comma-separated language codes
SOURCE_LANGUAGES = {
    # ── Local data sources (本地数据) ──
    "cbeta":            "lzh",
    "suttacentral":     "pi,en",
    "84000":            "bo,en,sa",
    "vri":              "pi",
    "sat":              "lzh,ja",
    "ddb":              "lzh,en,ja,ko",
    "kanseki-repo":     "lzh,sa",

    # ── Chinese collections (中国大陆) ──
    "nlc":              "lzh",
    "cnki-buddhism":    "lzh",
    "palace-museum":    "lzh",
    "cass-buddhism":    "lzh",
    "dunhuang-academy": "lzh,sa,bo",
    "peking-univ":      "lzh",
    "zhejiang-univ":    "lzh",
    "fudan-univ":       "lzh",
    "wuhan-univ":       "lzh",
    "renmin-univ":      "lzh",
    "nanjing-univ":     "lzh",
    "zhongshan-univ":   "lzh",
    "sichuan-univ":     "lzh",
    "lanzhou-univ":     "lzh",
    "northwest-univ":   "lzh",
    "inner-mongolia":   "lzh,cmg",
    "tibet-univ":       "bo,lzh",
    "southwest-minzu":  "bo,lzh",
    "minzu-univ":       "bo,lzh",
    "shanghai-museum":  "lzh",
    "national-museum-cn": "lzh",
    "suzhou-museum":    "lzh",
    "longquan-digital": "lzh",
    "nanputuo":         "lzh",
    "lingyin":          "lzh",
    "fgs-buddhism":     "lzh,en",
    "bailin":           "lzh",
    "baizhang":         "lzh",
    "china-buddhism-assoc": "lzh",
    "chinese-buddhist-canon": "lzh",

    # ── Taiwan (中国台湾) ──
    "cbeta-org":        "lzh",
    "dharma-drum":      "lzh,en",
    "dila":             "lzh,sa,pi,bo,en",
    "ncl-tw":           "lzh",
    "ntu-buddhism":     "lzh,en",
    "fgs-tw":           "lzh,en",
    "chung-hwa":        "lzh",
    "dharma-realm":     "lzh,en",
    "ddbc":             "lzh,en",

    # ── Japan (日本) ──
    "sat-utokyo":       "lzh,ja",
    "ndl-japan":        "lzh,ja",
    "tnm-japan":        "lzh,ja",
    "nara-museum":      "lzh,ja,sa",
    "waseda-kotenseki": "lzh,ja",
    "kyoto-univ":       "lzh,ja,sa",
    "otani-univ":       "lzh,ja,sa,bo",
    "komazawa-univ":    "lzh,ja",
    "taisho-univ":      "lzh,ja",
    "ryukoku-univ":     "lzh,ja",
    "toyo-bunko":       "lzh,ja,sa,bo",
    "bukkyo-dendo":     "lzh,ja,en",
    "iriz-hanazono":    "lzh,ja",
    "rkts-vienna":      "bo,sa",
    "icabs-tokyo":      "lzh,ja,sa",

    # ── Korea (韩国) ──
    "korean-tripitaka-db": "lzh,ko",
    "snu-kyujanggak":   "lzh,ko",
    "dongguk-univ":     "lzh,ko",
    "jogye-order":      "lzh,ko",

    # ── South & Southeast Asia ──
    "tbrc-bdrc":        "bo,sa,en",
    "lanka-encyclopedia": "si,pi,en",
    "nalanda-univ":     "sa,pi,en",
    "bhu-buddhism":     "sa,pi,en",
    "calcutta-univ":    "sa,pi,en",
    "mahabodhi":        "pi,en",
    "cscd-myanmar":     "pi,my",
    "thai-tripitaka":   "pi,th",
    "dhammakaya":       "pi,th,en",
    "mahachula-univ":   "pi,th,en",
    "preah-sihanouk":   "pi,km",

    # ── International digital projects ──
    "gretil":           "sa",
    "dsbc":             "sa",
    "gandhari":         "pgd",
    "polyglotta":       "sa,bo,lzh,pi,en",
    "budsir":           "pi,th",
    "ktk":              "lzh,ko",
    "accesstoinsight":  "pi,en",
    "suttacentral-org": "pi,en,lzh",
    "wisdom-lib":       "sa,pi,en",
    "dharmapearls":     "lzh,en",
    "ancient-buddhist":  "sa,pi,en",
    "84000-org":        "bo,sa,en",

    # ── Western universities & institutions ──
    "harvard-yenching":     "lzh,sa,bo,ja,en",
    "princeton-east-asian": "lzh,sa,ja,en",
    "stanford-buddhism":    "lzh,sa,en",
    "columbia-starr":       "lzh,ja,ko,en",
    "yale-east-asian":      "lzh,ja,en",
    "chicago-south-asian":  "sa,pi,bo,en",
    "berkeley-east-asian":  "lzh,ja,en",
    "michigan-asia":        "lzh,sa,en",
    "penn-south-asian":     "sa,pi,en",
    "oxford-bodleian":      "sa,pi,bo,en",
    "cambridge-sanskrit":   "sa,pi,en",
    "soas-london":          "sa,pi,bo,en",
    "bl-buddhism":          "sa,pi,bo,lzh,en",
    "bnf-buddhism":         "sa,pi,lzh,fr",
    "hamburg-csmc":         "sa,pgd,kho,sog,en,de",
    "munich-indology":      "sa,pi,bo,de",
    "vienna-tibetology":    "bo,sa,de",
    "leiden-kern":          "sa,pi,en",
    "ghent-buddhism":       "sa,pi,en",
    "toronto-buddhism":     "sa,pi,en",
    "ubc-buddhism":         "sa,lzh,en",
    "anu-buddhism":         "sa,pi,en",
    "sydney-buddhism":      "sa,pi,en",

    # ── Silk Road / Central Asian (丝路) ──
    "berlin-turfan":        "sa,kho,sog,xto,txb,oui,de",
    "turfan-studies":       "sa,kho,sog,xto,txb,oui,de",
    "ihp-dunhuang":         "lzh,bo,sa",
    "idp-bl":               "sa,kho,sog,xto,txb,lzh,bo",

    # ── Mongolia / Manchu / Tangut ──
    "mongolia-academy":     "cmg,bo",
    "tangut-xixia":         "txg,lzh",
    "manchu-studies":       "mnc,lzh",

    # ── Vietnamese ──
    "vn-buddhism":          "vi,lzh",

    # ── Museums ──
    "met-asian":            "sa,lzh,ja,en",
    "british-museum-asia":  "sa,pi,bo,lzh,en",
    "guimet-museum":        "sa,bo,lzh,fr",
    "asian-art-sf":         "sa,bo,lzh,en",
    "freer-sackler":        "sa,lzh,ja,en",
}


def upgrade() -> None:
    # Add languages column (comma-separated ISO 639 codes)
    op.add_column(
        "data_sources",
        sa.Column("languages", sa.String(200), nullable=True),
    )

    conn = op.get_bind()
    from sqlalchemy import text as sa_text

    for code, langs in SOURCE_LANGUAGES.items():
        conn.execute(
            sa_text("UPDATE data_sources SET languages = :langs WHERE code = :code"),
            {"code": code, "langs": langs},
        )

    # For any remaining sources without languages, set a sensible default based on region
    region_defaults = {
        "中国": "lzh",
        "中国大陆": "lzh",
        "中国台湾": "lzh",
        "台湾": "lzh",
        "日本": "lzh,ja",
        "韩国": "lzh,ko",
        "泰国": "pi,th",
        "缅甸": "pi,my",
        "斯里兰卡": "pi,si",
        "柬埔寨": "pi,km",
        "越南": "vi,lzh",
        "印度": "sa,pi,en",
        "尼泊尔": "sa,bo",
        "蒙古": "cmg,bo",
        "美国": "en,sa,lzh",
        "英国": "en,sa,pi",
        "德国": "de,sa",
        "法国": "fr,sa",
        "国际": "en,sa,pi",
    }
    for region, langs in region_defaults.items():
        conn.execute(
            sa_text(
                "UPDATE data_sources SET languages = :langs "
                "WHERE languages IS NULL AND region = :region"
            ),
            {"region": region, "langs": langs},
        )

    # Final fallback: any still NULL gets "lzh" (most are Chinese Buddhist sources)
    conn.execute(
        sa_text("UPDATE data_sources SET languages = 'lzh' WHERE languages IS NULL")
    )


def downgrade() -> None:
    op.drop_column("data_sources", "languages")
