"""Reactivate the CTER printed-canon source and retire its duplicate code.

Follow-up to 0162. The 2026-06-28 audit flagged cter.info (历代刻本汉文
藏经 PDF 影像) as a value-5 gap, but the INSERT in 0162 silently no-opped:
a row with code ``cter`` already existed (id 491, added in 0060) — it was
deactivated in 0063 as "low-value / redundant with CBETA". That redundancy
call does NOT hold: cter.info serves woodblock-print SCAN IMAGES (高丽/嘉兴/
永乐南北/洪武南藏, 79.6 GB / 6,701 PDFs), a different modality from CBETA's
punctuated digital text. So we reactivate the existing row rather than
insert a third one.

A duplicate code ``cter-info`` (same cter.info, added in 0082) does not
exist in the production DB but is created by 0082 in a from-scratch
migration run (e.g. CI). The UPDATE below retires it wherever it exists so
the catalog never shows two cter.info entries — a no-op in prod.

Reactivation resets health_status to 'ok' so the next health pass re-probes
it on clean network; base_url (https://cter.info/) and the existing
metadata are left untouched.

Revision ID: 0163
Revises: 0162
Create Date: 2026-06-28
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text as sa_text

revision: str = "0163"
down_revision: str | None = "0162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reactivate the canonical CTER row (id 491, code 'cter').
    op.execute(
        sa_text(
            """
            UPDATE data_sources
               SET is_active = true,
                   health_status = 'ok',
                   health_checked_at = NULL,
                   unreachable_since = NULL
             WHERE code = 'cter'
            """
        )
    )
    # Retire the redundant duplicate wherever it exists (no-op in prod).
    op.execute(
        sa_text(
            "UPDATE data_sources SET is_active = false WHERE code = 'cter-info'"
        )
    )


def downgrade() -> None:
    # Restore prior state: 'cter' was inactive (0063), 'cter-info' active (0082).
    op.execute(
        sa_text("UPDATE data_sources SET is_active = false WHERE code = 'cter'")
    )
    op.execute(
        sa_text("UPDATE data_sources SET is_active = true WHERE code = 'cter-info'")
    )
