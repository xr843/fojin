"""Retire twelve duplicate source rows; repoint NTU; fix one region label.

/sources is a directory readers mostly use to click out to other sites, so a
duplicate row is not harmless: it inflates the "612 sources" headline and shows
the same site twice under different names. Each pair below shares a base_url
(found by grouping active rows on their normalised URL) and was checked by hand —
pairs that share a domain but are genuinely different resources (the buddhaspace
dictionaries, the Cologne Sanskrit lexicons, Gallica sub-collections, …) stay.

Kept → retired (reason)
-----------------------
* ``ccbs-ntu`` → ``ntu-buddhism`` — same library. The site moved to
  ``dlbs.liberal.ntu.edu.tw`` (old host 301s there; title「臺大佛學數位圖書館」),
  which is why the probe flagged both rows ``moved``. The kept row follows it and
  inherits the search template (frontend searchPatterns.json).
* ``buddhason`` → ``suttafriends`` — both rows describe 莊春江's site and point at
  agama.buddhason.org. (suttafriends.org is an unrelated English site.)
* ``dila-authority`` → ``dila`` — same authority database; the kept row carries the
  three distributions.
* ``pali-dict-sutta`` → ``sutta-pali-dict`` — same site; kept row has the template.
* ``bdrc-ocr`` → ``buda-ocr-app`` — same GitHub repo.
* ``plumvillage-gems`` → ``plumvillage`` — same page; the retired row's description
  was an unedited note and it had no region.
* ``thl-uva`` → ``thl`` — identical name and site.
* ``vri`` → ``myanmar-tipitaka`` — tipitaka.org is VRI's site (the retired row
  wrongly attributed it to Dhammakaya); vri carries the 31 texts.
* ``heidelberg-buddhist-stone`` → ``stonesutras`` — same Heidelberg project.
* ``cttb-usa`` → ``btts-sutra-texts`` — same site; the retired row used http://,
  which has failed (HTTP 522) since 2026-05-19 while https serves fine.
* ``nlc`` → ``nlc-szgj`` — both point at read.nlc.cn.
* ``thuvienhoasen`` → ``vn-buddhism`` — same library.

Every retired row has zero references (texts, dictionary entries, identifiers,
distributions, IIIF manifests, updates — checked on prod 2026-10-19), so nothing
downstream moves. As in 0178, ``is_active = FALSE`` is the verb; nothing is deleted
and ``downgrade`` restores every row.

Region: ``buddhist-architecture-wiki`` was the only row labelled 「中国」, which the
i18n map renders as 「中国大陆」 — so the filter showed two 「中国大陆」 chips.

Revision ID: 0183
Revises: 0182
Create Date: 2026-10-19
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0183"
down_revision: str | None = "0182"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RETIRED_CODES = (
    "ntu-buddhism",
    "suttafriends",
    "dila",
    "sutta-pali-dict",
    "buda-ocr-app",
    "plumvillage",
    "thl",
    "myanmar-tipitaka",
    "stonesutras",
    "btts-sutra-texts",
    "nlc-szgj",
    "vn-buddhism",
)

NTU_NEW_URL = "https://dlbs.liberal.ntu.edu.tw/"
NTU_OLD_URL = "http://buddhism.lib.ntu.edu.tw/"


def _set_active(active: bool) -> None:
    op.execute(
        sa_text("UPDATE data_sources SET is_active = :active WHERE code = ANY(:codes)").bindparams(
            active=active, codes=list(RETIRED_CODES)
        )
    )


def _set_ntu(url: str, supports_search: bool) -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = :url,
                   supports_search = :supports_search
             WHERE code = 'ccbs-ntu'
            """
        ).bindparams(url=url, supports_search=supports_search)
    )


def _clear_ntu_health() -> None:
    """Drop the ``moved`` verdict earned by the old hostname, as 0166/0177/0178 did."""
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET health_status = 'ok',
                   health_checked_at = NULL,
                   health_detail = NULL,
                   health_confidence = 'high',
                   unreachable_since = NULL
             WHERE code = 'ccbs-ntu'
            """
        )
    )


def _set_region(old: str, new: str) -> None:
    op.execute(
        sa_text(
            "UPDATE data_sources SET region = :new WHERE code = 'buddhist-architecture-wiki' AND region = :old"
        ).bindparams(old=old, new=new)
    )


def upgrade() -> None:
    _set_active(False)
    _set_ntu(NTU_NEW_URL, True)
    _clear_ntu_health()
    _set_region("中国", "中国大陆")


def downgrade() -> None:
    _set_region("中国大陆", "中国")
    _set_ntu(NTU_OLD_URL, False)
    _set_active(True)
