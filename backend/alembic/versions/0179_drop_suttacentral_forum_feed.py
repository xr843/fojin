"""Stop carrying SuttaCentral forum posts; delete the stored copies.

Revision ID: 0179
Revises: 0178
Create Date: 2026-09-13

``suttacentral_forum`` joined the academic-feed registry on 2026-06-11. It is
removed from ``scripts/fetch_academic_feeds.py`` in the same change; this
migration removes what the daily cron had already stored.

Why, in two facts checked on 2026-09-13:

* **Forum posts are not SuttaCentral's CC0 dedication.** The CC0 covers the
  texts and translations (``suttacentral/bilara-data`` ``LICENSE.md``). The
  forum ToS §3 licenses user contributions under CC BY-NC-SA 3.0, with
  copyright staying with each poster.
* **The feed stored near-full copies.** Discourse puts the whole first post in
  the RSS ``<description>``: 256 posts in production, median 941 chars, 18%
  hitting the 2,000-char cap — shown on /activity with author and link but
  without the license notice BY 3.0 §4(a) requires. (Tricycle, by contrast,
  ships excerpts: median 182 chars.)

This does not touch SuttaCentral's CC0 texts, translations, glossary or
parallels, which remain in use with attribution.

Downgrade is a no-op on purpose: the rows were copies of third-party posts,
not FoJin data, and putting them back would restore the problem being fixed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0179"
down_revision: str | None = "0178"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM academic_feeds WHERE feed_source = 'suttacentral_forum'")


def downgrade() -> None:
    pass
