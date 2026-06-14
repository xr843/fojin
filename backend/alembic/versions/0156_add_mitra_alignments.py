"""add mitra_alignments table for MITRA cross-lingual parallel passages

Revision ID: 0156
Revises: 0155
Create Date: 2026-06-14

Stores sentence-level Sanskrit/Tibetan ↔ Buddhist-Chinese parallels mined by
the MITRA project (Nehrdich & Keutzer, arXiv:2601.06400,
github.com/dharmamitra/mitra-parallel, CC BY-SA 4.0).

Why a separate table instead of alignment_pairs: alignment_pairs is a
"fojin-chunk ↔ fojin-chunk" model — the reader API resolves the *other* side by
looking up text_embeddings.chunk_text. MITRA's foreign side is an *inline*
Sanskrit/Tibetan sentence that has no corresponding fojin text_embeddings row
(we do not ingest the Skt/Tib source texts as chunks), so it cannot be expressed
in alignment_pairs. mitra_alignments stores the foreign text inline and anchors
only the Chinese side to a fojin chunk (text_id, juan_num, chunk_index), located
by verbatim substring match of the MITRA Chinese sentence inside the juan.

Provenance/license is kept per-row (source, license) so this CC BY-SA 4.0 data
stays attributable and license-separable from fojin's own alignment_pairs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0156"
down_revision: str | None = "0155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mitra_alignments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("taisho_id", sa.String(length=20), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("zh_text", sa.Text(), nullable=False),
        sa.Column("foreign_lang", sa.String(length=4), nullable=False),
        sa.Column("foreign_text", sa.Text(), nullable=False),
        sa.Column("zh_segment", sa.String(length=80), nullable=True),
        sa.Column("foreign_segment", sa.String(length=80), nullable=True),
        sa.Column("mitra_file", sa.String(length=160), nullable=True),
        sa.Column("match_scope", sa.String(length=8), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="mitra-parallel"),
        sa.Column("license", sa.String(length=20), nullable=False, server_default="CC-BY-SA-4.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["text_id"], ["buddhist_texts.id"], name="fk_mitra_align_text", ondelete="CASCADE"
        ),
    )
    # Reader panel lookup: parallels for one (text_id, juan_num, chunk_index).
    op.create_index(
        "ix_mitra_align_chunk",
        "mitra_alignments",
        ["text_id", "juan_num", "chunk_index"],
    )
    op.create_index("ix_mitra_align_taisho", "mitra_alignments", ["taisho_id"])
    # Idempotent re-import: an import run wipes its own (text_id) rows first.
    op.create_index("ix_mitra_align_text", "mitra_alignments", ["text_id"])


def downgrade() -> None:
    op.drop_index("ix_mitra_align_text", table_name="mitra_alignments")
    op.drop_index("ix_mitra_align_taisho", table_name="mitra_alignments")
    op.drop_index("ix_mitra_align_chunk", table_name="mitra_alignments")
    op.drop_table("mitra_alignments")
