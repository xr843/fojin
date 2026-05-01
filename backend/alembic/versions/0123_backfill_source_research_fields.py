"""Backfill research_fields for 28 sources flagged by the audit.

Sources page audit (2026-05-01) found 28 active sources with NULL
research_fields, mostly classical Chinese Buddhist dictionaries and a few
multilingual reference works. Without a tag they vanish from the eight-
category research filter on /sources.

Buckets:
- 'dictionary,han'       : 21 classical Chinese dictionaries / reference works
- 'dictionary,theravada' : DPPN (Pali proper names)
- 'dictionary,theravada,han'   : Buddhadatta Pali → Chinese
- 'dictionary,sanskrit'  : Apte Sanskrit-English
- 'dictionary,sanskrit,han'    : Mahāvyutpatti (Sa↔Zh)
- 'dictionary,han,sanskrit'    : Siyi Hebi (Sa/Mn/Mnc/Zh polyglot)
- 'dictionary,han,tibetan,sanskrit' : Pentaglot
- 'art'                  : Cambridge Digital Library (manuscript images)

Revision ID: 0123
Revises: 0122
"""

from alembic import op
from sqlalchemy import text

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None

BUCKETS: dict[str, list[str]] = {
    "dictionary,han": [
        "foguang", "zhonghua-baike", "bs-faxiang", "weishi", "tiantai",
        "dila-nanshanlu", "abhidharma", "sanzang-fashu", "fanyi-mingyi",
        "suyu-foyuan", "bs-yiqiejing-yinyi", "bs-xu-yinyi", "bs-suihan-lu",
        "bs-fanfanyu", "bs-agama", "bs-changjianci", "fxcd-tongbian",
        "zuting-shiyuan", "chanzong-tiyao", "shishi-yaolan", "yuezang-zhijin",
    ],
    "dictionary,theravada": ["dppn"],
    "dictionary,theravada,han": ["dila-plc"],
    "dictionary,sanskrit": ["cdsl-apte"],
    "dictionary,sanskrit,han": ["dila-mvp"],
    "dictionary,han,sanskrit": ["siyi-hebi"],
    "dictionary,han,tibetan,sanskrit": ["dila-ptg"],
    "art": ["cudl"],
}


def upgrade() -> None:
    conn = op.get_bind()
    # Idempotent: only fill when current value is NULL or empty, never overwrite
    # an explicit choice made later.
    for fields, codes in BUCKETS.items():
        conn.execute(
            text(
                "UPDATE data_sources "
                "SET research_fields = :fields "
                "WHERE code = ANY(:codes) "
                "AND (research_fields IS NULL OR research_fields = '')"
            ),
            {"fields": fields, "codes": codes},
        )


def downgrade() -> None:
    # Reverting blanks all 28 back to NULL.
    conn = op.get_bind()
    all_codes = [c for codes in BUCKETS.values() for c in codes]
    conn.execute(
        text("UPDATE data_sources SET research_fields = NULL WHERE code = ANY(:codes)"),
        {"codes": all_codes},
    )
