"""add mitra_e_score quality column to mitra_alignments

Revision ID: 0169
Revises: 0168
Create Date: 2026-07-11

mitra_alignments.confidence is a constant 1.0 import flag, NOT a quality
score (see the catalog notes in app/api/alignment.py). Real per-pair quality
lands in this new nullable mitra_e_score column, backfilled offline by
scripts/backfill_mitra_scores.py — a BGE-M3 cosine PROXY for now, replaced by
the MITRA-E semantic gate later. NULL means "not yet scored", which is what
makes the backfill resumable (WHERE mitra_e_score IS NULL).

Index design — the anticipated read path filters "parallels for chunk X above
a score threshold", i.e. the existing ix_mitra_align_chunk lookup pattern plus
`AND mitra_e_score >= 0.30`. One partial composite index serves it:

- leading (text_id, juan_num, chunk_index) matches the chunk-lookup pattern;
- trailing mitra_e_score lets Postgres apply ANY `>= threshold` predicate
  inside the index, so calibration can move the cutoff without a rebuild
  (a hard-coded `WHERE mitra_e_score >= 0.30` partial was rejected because
  the threshold is uncalibrated — see the backfill script docstring);
- the `IS NOT NULL` predicate keeps the index empty until the backfill runs
  (the whole table is NULL at migration time) and afterwards only as large as
  the scored subset. Any `mitra_e_score >= x` query qualifies for the partial
  index because `>= x` implies IS NOT NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0169"
down_revision: str | None = "0168"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mitra_alignments", sa.Column("mitra_e_score", sa.Float(), nullable=True))
    op.create_index(
        "ix_mitra_align_chunk_escore",
        "mitra_alignments",
        ["text_id", "juan_num", "chunk_index", "mitra_e_score"],
        postgresql_where=sa.text("mitra_e_score IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_mitra_align_chunk_escore", table_name="mitra_alignments")
    op.drop_column("mitra_alignments", "mitra_e_score")
