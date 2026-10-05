"""SAT source links open the sutra, not SAT's homepage.

Revision ID: 0180
Revises: 0179
Create Date: 2026-10-05

76 ``text_identifiers`` rows link to SAT as
``https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?no=0235``. Checked in a
browser on 2026-10-05: that URL opens SAT's「このサイトについて」page and never
loads the text — the reader's「来源：SAT 大正藏数据库」link has been a dead end.
``SAT2018/T0235.html`` opens the text. (curl cannot tell them apart: SAT serves
the same JS shell for every path, so the check has to be done in a browser.)

Only rows exactly matching the four-digit ``master30.php?no=`` form are touched
(a read-only dry run on production matched all 76, one distinct target each).
Downgrade restores the original form for the same rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0180"
down_revision: str | None = "0179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = r"^https://21dzk\.l\.u-tokyo\.ac\.jp/SAT2018/master30\.php\?no=([0-9]{4})$"
_NEW = r"^https://21dzk\.l\.u-tokyo\.ac\.jp/SAT2018/T([0-9]{4})\.html$"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE text_identifiers
           SET source_url = regexp_replace(source_url, '{_OLD}',
                                           'https://21dzk.l.u-tokyo.ac.jp/SAT2018/T\\1.html')
         WHERE source_url ~ '{_OLD}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE text_identifiers
           SET source_url = regexp_replace(source_url, '{_NEW}',
                                           'https://21dzk.l.u-tokyo.ac.jp/SAT2018/master30.php?no=\\1')
         WHERE source_url ~ '{_NEW}'
        """
    )
