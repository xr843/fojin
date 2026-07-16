"""add chat_answer_diagnostics.quote_checked_count

Revision ID: 0171
Revises: 0170
Create Date: 2026-07-16

Persist how many 「…」 quotes an answer had verbatim-checked — the value
count_checked_quotes() returns, now also surfaced on ChatTrustStatus so admin
/eval and historical (diagnostic-reconstructed) answers see it, not just the
live response.

Nullable with NO server_default on purpose: rows written before this migration
were never scored for it, and NULL ("unknown / not recorded") must stay
distinguishable from 0 ("cited but quoted nothing verbatim") — the very
distinction this column exists to make. New writes always set an integer via
persist_answer_diagnostic.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0171"
down_revision: str | None = "0170"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_answer_diagnostics",
        sa.Column("quote_checked_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_answer_diagnostics", "quote_checked_count")
