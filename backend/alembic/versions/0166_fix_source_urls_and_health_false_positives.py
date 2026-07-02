"""Fix two source URL health false positives and the stale GRETIL distribution.

The 2026-07-02 source-health audit found two narrow data issues that should be
fixed in data, not by bulk-clearing every red badge:

* ``indica-buddhica-repo`` was set to ``https://indica-et-buddhica.org/repositorium``
  in 0162. That URL now redirects to the live publisher homepage, while
  ``https://indica-et-buddhica.com/repositorium`` returns 404. Use the current
  live homepage and clear only this row's stale health fields.
* ``gretil-github-mirror`` points at a GitHub repository that returns 404.
  Repoint the distribution at the official GRETIL HTML index. The archived
  ``scripts/archive/imports/import_gretil.py`` importer already uses the
  official GRETIL path directly, so this catalog distribution is not a hard
  dependency for that script.

Revision ID: 0166
Revises: 0165
Create Date: 2026-07-02
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0166"
down_revision: str | None = "0165"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDICA_BUDDHICA_URL = "https://indica-et-buddhica.com/"
PREVIOUS_INDICA_BUDDHICA_URL = "https://indica-et-buddhica.org/repositorium"
CLEAR_HEALTH_CODES = ("indica-buddhica-repo",)

GRETIL_DISTRIBUTION_CODE = "gretil-github-mirror"
GRETIL_DISTRIBUTION_UPDATE = {
    "name": "GRETIL Official HTML Index",
    "channel_type": "bulk_dump",
    "url": "https://gretil.sub.uni-goettingen.de/gretil.html",
    "format": "html",
    "license_note": (
        "Official GRETIL HTML index with cumulative download links and per-text "
        "TEI/txt files. Catalog pointer only; not a hard dependency for "
        "scripts/archive/imports/import_gretil.py, which reads the official "
        "GRETIL path directly."
    ),
    "is_primary_ingest": True,
    "priority": 10,
    "is_active": True,
}
GRETIL_DISTRIBUTION_PREVIOUS = {
    "name": "GRETIL GitHub Mirror",
    "channel_type": "git",
    "url": "https://github.com/gretil-corpus/gretil-corpus-tei-2024",
    "format": "tei/xml",
    "license_note": "GRETIL 梵文文本 TEI 格式 GitHub 镜像，公共领域。推荐主导入源。",
    "is_primary_ingest": True,
    "priority": 10,
    "is_active": True,
}


def _set_indica_url(url: str) -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET base_url = :url
             WHERE code = 'indica-buddhica-repo'
            """
        ).bindparams(url=url)
    )


def _clear_stale_health() -> None:
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET health_status = 'ok',
                   health_checked_at = NULL,
                   health_detail = NULL,
                   unreachable_since = NULL
             WHERE code = 'indica-buddhica-repo'
            """
        )
    )


def _set_gretil_distribution(values: dict[str, object]) -> None:
    op.execute(
        sa_text(
            """
            UPDATE source_distributions
               SET name = :name,
                   channel_type = :channel_type,
                   url = :url,
                   format = :format,
                   license_note = :license_note,
                   is_primary_ingest = :is_primary_ingest,
                   priority = :priority,
                   is_active = :is_active
             WHERE code = :code
            """
        ).bindparams(code=GRETIL_DISTRIBUTION_CODE, **values)
    )


def upgrade() -> None:
    _set_indica_url(INDICA_BUDDHICA_URL)
    _clear_stale_health()
    _set_gretil_distribution(GRETIL_DISTRIBUTION_UPDATE)


def downgrade() -> None:
    _set_gretil_distribution(GRETIL_DISTRIBUTION_PREVIOUS)
    _set_indica_url(PREVIOUS_INDICA_BUDDHICA_URL)
