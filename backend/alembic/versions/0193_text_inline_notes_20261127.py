"""CBETA inline notes (夹注 / 双行小注) table.

The parser has always dropped every <note>, including <note place="inline"> — part of the
original text (e.g. every gloss in 一切經音義, the translation dates in 開元釋教錄). 3,458
works lost ~12M characters this way. The notes are stored apart from TextContent.content so
the body text — and every offset into it (line anchors, apparatus, quote highlights, search,
embeddings) — stays exactly as it is; the reader splices them back in by offset.

Additive only: a new table, filled by scripts/import_inline_notes.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0193"
down_revision: str | None = "0192"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "text_inline_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("char_offset", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_text_inline_notes_text_juan", "text_inline_notes", ["text_id", "juan_num", "seq"])


def downgrade() -> None:
    op.drop_index("ix_text_inline_notes_text_juan", table_name="text_inline_notes")
    op.drop_table("text_inline_notes")
