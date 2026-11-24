"""Study memory settings: per-user switch + self-written answer preferences.

/chat started every conversation blank: it did not know what the reader was
studying, what they had asked before, or how they wanted things explained. The
memory itself is derived on the fly from rows that already exist (reading
history, recent conversation titles, excerpts); this table only stores what the
reader controls — whether Xiaojin may use it, and a short note in their own words.

Additive only: a new table, no existing data touched. No row = memory on, no note.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0192"
down_revision: str | None = "0191"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_study_memory",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_study_memory")
