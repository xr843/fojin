"""backfill license/rights metadata for 14 primary-source rows

Revision ID: 0149
Revises: 0148
Create Date: 2026-06-10

WebFetch-verified against upstream ToS on 2026-06-10. Sub-sources are
grouped by upstream provider (CBETA / 84000 / SuttaCentral / BDRC).
"cbeta-rag-opensource" is intentionally excluded — appears to be a
reference-implementation repo whose content provenance is separate.
GRETIL is not currently in fojin sources, so it is not addressed here.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0149"
down_revision: Union[str, None] = "0148"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CBETA_CODES = (
    "cbeta-api",
    "jinglu-cbeta",
    "cbeta-tripitaka",
    "cbeta-archive",
    "cbeta-concordance",
    "cbeta-mcp",
)
KOO_CODES = ("84000", "namo84000", "84000-glossary")
SC_CODES = ("suttacentral", "suttacentral-voice")
BDRC_CODES = ("bdrc-khmer", "bdrc-nlm", "bdrc-ocr")

ALL_BACKFILLED = CBETA_CODES + KOO_CODES + SC_CODES + BDRC_CODES


def _tuple_sql(codes: Sequence[str]) -> str:
    return "(" + ", ".join(f"'{c}'" for c in codes) + ")"


def upgrade() -> None:
    # 84000 — CC-BY-NC-ND-4.0. ToS explicitly permits AI/ML training as
    # fair use (no traceable copy remains after training). Most RAG-friendly.
    op.execute(
        f"""
        UPDATE data_sources SET
            license_spdx='CC-BY-NC-ND-4.0',
            license_url='https://creativecommons.org/licenses/by-nc-nd/4.0/',
            attribution_required=true,
            commercial_allowed=false,
            redistribution_allowed=true,
            embedding_allowed=true,
            license_notes='84000 ToS (https://84000.co/documents/terms-of-use) explicitly permits AI/ML training as fair use. Attribution required: cite 84000 as source.',
            license_verified_at=NOW()
        WHERE code IN {_tuple_sql(KOO_CODES)}
        """
    )

    # SuttaCentral bilara-data — CC0-1.0 mandated for all supported translations.
    # Pali source texts also free of restrictions (public domain by age).
    op.execute(
        f"""
        UPDATE data_sources SET
            license_spdx='CC0-1.0',
            license_url='https://creativecommons.org/publicdomain/zero/1.0/',
            attribution_required=false,
            commercial_allowed=true,
            redistribution_allowed=true,
            embedding_allowed=true,
            license_notes='SuttaCentral mandates CC0 for all bilara-data translations. Pali source texts treated as public domain.',
            license_verified_at=NOW()
        WHERE code IN {_tuple_sql(SC_CODES)}
        """
    )

    # CBETA — CC-BY-NC-SA-3.0-TW. Note: SPDX list has CC-BY-NC-SA-3.0; the
    # Taiwan port is denoted via license_url. ToS does NOT explicitly address
    # AI/ML embedding, so embedding_allowed stays NULL (= not verified) —
    # fojin's current RAG embedding behavior for CBETA content is a
    # compliance gray area pending direct clarification from CBETA.
    op.execute(
        f"""
        UPDATE data_sources SET
            license_spdx='CC-BY-NC-SA-3.0',
            license_url='https://creativecommons.org/licenses/by-nc-sa/3.0/tw/',
            attribution_required=true,
            commercial_allowed=false,
            redistribution_allowed=true,
            embedding_allowed=NULL,
            license_notes='CBETA Taiwan CC-BY-NC-SA-3.0-TW. THREE COLLECTIONS EXCLUDED FROM CC and require separate permissions: 印順法師佛學著作集, 太虛大師全書, 呂澂佛學著作集. AI/ML embedding NOT explicitly addressed in ToS — fojin should consult CBETA before scaling RAG indexing.',
            license_verified_at=NOW()
        WHERE code IN {_tuple_sql(CBETA_CODES)}
        """
    )

    # BDRC — per-resource license varies (catalog metadata vs scan images vs
    # OCR text differ; source library holder may also impose restrictions).
    # ToS page could not be located via WebFetch on 2026-06-10. Marked
    # unknown to surface in audit queries.
    op.execute(
        f"""
        UPDATE data_sources SET
            license_spdx='unknown',
            attribution_required=NULL,
            commercial_allowed=NULL,
            redistribution_allowed=NULL,
            embedding_allowed=NULL,
            license_notes='BDRC content has per-resource licensing (catalog metadata vs scan images vs OCR text differ). ToS page not located 2026-06-10. fojin must verify per-resource license before mass ingest / embedding.',
            license_verified_at=NOW()
        WHERE code IN {_tuple_sql(BDRC_CODES)}
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE data_sources SET
            license_spdx=NULL,
            license_url=NULL,
            license_notes=NULL,
            attribution_required=NULL,
            commercial_allowed=NULL,
            redistribution_allowed=NULL,
            embedding_allowed=NULL,
            license_verified_at=NULL
        WHERE code IN {_tuple_sql(ALL_BACKFILLED)}
        """
    )
