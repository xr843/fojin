"""Set supports_api / supports_iiif on sources added in 0133, 0134, 0141.

Those three migrations inserted 39 sources but reused the 0132 column set,
which omits supports_api / supports_iiif — so every new source defaulted to
false on both. The /sources page capability badges (影像 / API) are computed
live from these flags, so the counts under-reported the new museum, API and
manuscript-imaging sources.

Verified each candidate against its live site (REST API docs, IIIF manifests,
high-res scan delivery). supports_iiif follows fojin's broad definition:
"IIIF service OR high-resolution scanned imagery".

  supports_api  (5): the five museum open-data APIs — Met, Cleveland, Harvard,
                     Smithsonian, V&A — all ship documented machine-readable
                     REST/JSON APIs.
  supports_iiif (11): the five above (all serve IIIF or high-res imagery) plus
                     rubin-museum, utsbm-tokyo, tmpv-vienna, femc-khmer,
                     sac-manuscripts, eap791-lanten (manuscript/art scans).

Left false (no evidence found): asianart-sf, ngmcp-hamburg,
indica-buddhica-repo, webuddhist, tidl.

Revision ID: 0142
Revises: 0141
Create Date: 2026-05-17
"""

from alembic import op
from sqlalchemy import text

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None

API_SOURCES = (
    "met-openaccess",
    "cleveland-art-api",
    "harvard-art-api",
    "si-asian-art-oa",
    "va-museum",
)

IIIF_SOURCES = (
    "met-openaccess",
    "cleveland-art-api",
    "harvard-art-api",
    "si-asian-art-oa",
    "va-museum",
    "rubin-museum",
    "utsbm-tokyo",
    "tmpv-vienna",
    "femc-khmer",
    "sac-manuscripts",
    "eap791-lanten",
)


def _set_flag(column: str, codes: tuple[str, ...], value: bool) -> None:
    # codes are fixed ASCII slugs — safe to inline; an inline IN-list also
    # renders under `alembic --sql` offline mode (a bound list does not).
    in_list = ", ".join(f"'{c}'" for c in codes)
    op.execute(
        text(f"UPDATE data_sources SET {column} = {str(value).lower()} WHERE code IN ({in_list})")
    )


def upgrade() -> None:
    _set_flag("supports_api", API_SOURCES, True)
    _set_flag("supports_iiif", IIIF_SOURCES, True)


def downgrade() -> None:
    _set_flag("supports_api", API_SOURCES, False)
    _set_flag("supports_iiif", IIIF_SOURCES, False)
