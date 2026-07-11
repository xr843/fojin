"""Alignment anchor foundation: stable chunk identity + char-offset anchors.

Revision ID: 0168
Revises: 0167
Create Date: 2026-07-11

Two foundations so cross-canon alignments can survive re-chunking:

1. ``uq_text_embeddings_pos`` — unique (text_id, juan_num, chunk_index) on
   text_embeddings. All three alignment stores (alignment_pairs,
   mitra_alignments, and the reader deep-links) reference chunks POSITIONALLY
   by this triple with no FK, so a duplicate position silently corrupts every
   positional lookup. Pre-existing duplicates are deleted keeping the lowest
   id per position — embeddings are regenerated from text_contents by the
   import pipeline (see scripts/repair_stale_embeddings.py), so dropping
   surplus copies loses nothing that cannot be rebuilt.

2. Nullable char-offset columns on alignment_pairs
   (text_a_char_start/text_a_char_end + b-side): offsets into the juan's
   text_contents.content — the re-chunking-stable anchor (same model as
   text_apparatus.char_start/char_end from 0158). Backfilled by
   scripts/backfill_alignment_offsets.py; left NULL until then.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0168"
down_revision: str | None = "0167"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Dedupe before constraining: the unique constraint cannot be created while
    # duplicate (text_id, juan_num, chunk_index) rows exist. Keep the lowest id
    # per position. Safe to delete: embeddings are regenerable from
    # text_contents, and every positional consumer resolves the triple to ONE
    # row anyway — the surplus copies were already unreachable-by-intent.
    op.execute(
        sa.text(
            """
            DELETE FROM text_embeddings a
            USING text_embeddings b
            WHERE a.text_id = b.text_id
              AND a.juan_num = b.juan_num
              AND a.chunk_index = b.chunk_index
              AND a.id > b.id
            """
        )
    )
    op.create_unique_constraint(
        "uq_text_embeddings_pos",
        "text_embeddings",
        ["text_id", "juan_num", "chunk_index"],
    )

    # Char offsets of each side's chunk within its juan's text_contents.content
    # (the content row whose lang matches the side's text_{a,b}_lang). Nullable:
    # populated by scripts/backfill_alignment_offsets.py and by future writers.
    op.add_column("alignment_pairs", sa.Column("text_a_char_start", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_a_char_end", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_b_char_start", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_b_char_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("alignment_pairs", "text_b_char_end")
    op.drop_column("alignment_pairs", "text_b_char_start")
    op.drop_column("alignment_pairs", "text_a_char_end")
    op.drop_column("alignment_pairs", "text_a_char_start")
    op.drop_constraint("uq_text_embeddings_pos", "text_embeddings", type_="unique")
    # Duplicate text_embeddings rows deleted in upgrade() are NOT restored:
    # they carried no information (regenerable embeddings of identical chunks).
