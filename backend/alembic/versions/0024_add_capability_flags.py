"""P2: add capability flags to data_sources and backfill from known data

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 4 capability flag columns
    op.add_column("data_sources", sa.Column("supports_search", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("data_sources", sa.Column("supports_fulltext", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("data_sources", sa.Column("supports_iiif", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("data_sources", sa.Column("supports_api", sa.Boolean(), server_default="false", nullable=False))
    print("✅ Added 4 capability flag columns")

    conn = op.get_bind()

    # ── Backfill supports_search: sources that have known search URL patterns ──
    # This list mirrors the SEARCH_PATTERNS keys in frontend/src/utils/sourceUrls.ts
    searchable_codes = [
        "cbeta-org", "cbeta", "cbeta-api", "suttacentral-org", "suttacentral",
        "accesstoinsight", "tbrc-bdrc", "bdrc", "kanseki-repo", "wisdom-lib",
        "dharmapearls", "ddb", "sat-utokyo", "sat", "dila", "dharma-drum",
        "ctext", "84000",
        "digital-pali-reader", "tipitaka-org", "dhammatalks", "palikanon",
        "dhammawiki", "buddhanet", "pali-text-society", "suttafriends",
        "lotsawa-house", "buddhanexus", "treasury-of-lives", "rigpa-wiki", "adarsha",
        "sarit", "gretil", "dsbc",
        "nlc", "ndl-japan", "loc-asian", "bl-buddhism", "bnf-buddhism", "ncl-tw",
        "harvard-yenching", "waseda-kotenseki", "kyoto-univ", "snu-kyujanggak",
        "ntu-buddhism", "princeton-east-asian", "stanford-buddhism", "columbia-starr",
        "korean-tripitaka-db", "haeinsa",
        "inbuds", "iriz-hanazono", "komazawa-univ",
        "cnki-buddhism", "academia-sinica", "fgs-digital",
        "palace-museum", "nara-museum", "tnm-japan",
        "turfan-studies", "berlin-turfan",
        "dunhuang-academy", "idp",
        "buddhistdoor",
        # 0022 batch
        "tipitakapali-org", "tipitaka-app", "tipitaka-lk", "dpd-dict",
        "cpd-cologne", "pali-dict-sutta", "ped-dsal", "pali-canon-online",
        "tibetan-buddhist-encyclopedia", "monlam-ai", "openpecha", "rywiki",
        "adarsha-pechamaker", "nitartha-dict",
        "dcs-sanskrit", "cdsl-cologne", "titus-thesaurus", "gandhari-texts-sydney",
        "stonesutras", "foguang-dict", "nti-reader", "frogbear",
        "jinglu-cbeta", "acmuller-dict", "lancaster-catalog", "ddm-library",
        "koreanbuddhism", "himalayan-art",
        "btts", "open-buddhist-univ", "h-buddhism-zotero", "dila-glossaries", "mitra-ai",
        "jbe-ethics", "jgb-global", "jiabs",
        "audiodharma", "dharmaseed", "free-buddhist-audio",
        # 0023 batch
        "dharmacloud", "compassion-network", "otdo", "ltwa-resource",
        "dtab-bonn", "cudl-cambridge", "digital-bodleian", "dharma-torch",
    ]
    if searchable_codes:
        placeholders = ", ".join(f":c{i}" for i in range(len(searchable_codes)))
        params = {f"c{i}": code for i, code in enumerate(searchable_codes)}
        conn.execute(sa.text(
            f"UPDATE data_sources SET supports_search = true WHERE code IN ({placeholders})"
        ), params)
    search_result = conn.execute(sa.text(
        "SELECT count(*) FROM data_sources WHERE supports_search = true"
    )).scalar()
    print(f"✅ Backfilled supports_search for {search_result} sources")

    # ── Backfill supports_fulltext: sources with local content ──
    fulltext_codes = [
        "cbeta", "cbeta-org", "cbeta-api",  # CBETA local content
        "suttacentral", "suttacentral-org",  # SC with imported content
    ]
    if fulltext_codes:
        placeholders = ", ".join(f":c{i}" for i in range(len(fulltext_codes)))
        params = {f"c{i}": code for i, code in enumerate(fulltext_codes)}
        conn.execute(sa.text(
            f"UPDATE data_sources SET supports_fulltext = true WHERE code IN ({placeholders})"
        ), params)
    print(f"✅ Backfilled supports_fulltext for {len(fulltext_codes)} sources")

    # ── Backfill supports_iiif: sources with known IIIF support ──
    iiif_codes = [
        "idp", "sat-iiif", "dunhuang-iiif", "dunhuang-academy",
        "otdo", "dtab-bonn", "cudl-cambridge", "digital-bodleian",
        "waseda-kotenseki", "bnf-buddhism", "bl-buddhism",
        "eap-bl", "ngmcp", "palace-museum", "nara-museum", "tnm-japan",
        "shosoin", "schoyen-collection", "otani-collection",
    ]
    if iiif_codes:
        placeholders = ", ".join(f":c{i}" for i in range(len(iiif_codes)))
        params = {f"c{i}": code for i, code in enumerate(iiif_codes)}
        conn.execute(sa.text(
            f"UPDATE data_sources SET supports_iiif = true WHERE code IN ({placeholders})"
        ), params)
    print(f"✅ Backfilled supports_iiif for {len(iiif_codes)} sources")

    # ── Backfill supports_api: sources with known API ──
    api_codes = [
        "ctext", "openpecha", "buddhanexus", "cbeta-api",
        "suttacentral", "suttacentral-org", "bdrc", "tbrc-bdrc",
        "dila", "dila-glossaries",
    ]
    if api_codes:
        placeholders = ", ".join(f":c{i}" for i in range(len(api_codes)))
        params = {f"c{i}": code for i, code in enumerate(api_codes)}
        conn.execute(sa.text(
            f"UPDATE data_sources SET supports_api = true WHERE code IN ({placeholders})"
        ), params)
    print(f"✅ Backfilled supports_api for {len(api_codes)} sources")


def downgrade() -> None:
    op.drop_column("data_sources", "supports_api")
    op.drop_column("data_sources", "supports_iiif")
    op.drop_column("data_sources", "supports_fulltext")
    op.drop_column("data_sources", "supports_search")
