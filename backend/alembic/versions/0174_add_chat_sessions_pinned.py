"""Add chat_sessions.pinned.

The sidebar lists a user's conversations newest-first, which is the wrong order
for the few a reader actually returns to: a long-running study thread on a
single sutra sinks below a week of one-off questions. Pinning is the standard
answer and needs exactly one bit per session.

Boolean rather than a `pinned_at` timestamp: ordering *within* the pinned group
only matters once a user has pinned enough conversations to need it, and the
group is rendered as its own section at the top of the list. Falling back to
`created_at desc` inside it keeps the ordering rule identical to the rest of
the list, which is the less surprising behaviour.

Defaults to false, so every existing row keeps its current position.

Revision ID: 0174
Revises: 0173
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0174"
down_revision: str | None = "0173"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "pinned")
