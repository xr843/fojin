"""Personal reader excerpts (private highlights with optional note).

Readers asked (2026-11-24) for highlight / underline / save-passage in the reader.
The existing ``annotations`` table is public and moderated; 2 of its 4 rows ever
were readers pasting sutra lines in as personal excerpts and getting rejected.
This table is private to the owner and never reviewed.

Additive only: a new table, no existing data touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0191"
down_revision: str | None = "0190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_excerpts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("line_ref", sa.String(16), nullable=True),
        sa.Column("end_line_ref", sa.String(16), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_excerpts_user_id", "user_excerpts", ["user_id"])
    op.create_index("ix_user_excerpts_user_text_juan", "user_excerpts", ["user_id", "text_id", "juan_num"])


def downgrade() -> None:
    op.drop_index("ix_user_excerpts_user_text_juan", table_name="user_excerpts")
    op.drop_index("ix_user_excerpts_user_id", table_name="user_excerpts")
    op.drop_table("user_excerpts")
