"""add sentence_alignments table for sentence-level cross-canon alignment

Revision ID: 0170
Revises: 0169
Create Date: 2026-07-11

Package C of the alignment moat: a NEW dedicated table, NOT an extension of
alignment_pairs. A sentence alignment SUBDIVIDES a known chunk-level pair's
char-offset spans (the anchors from 0168) into aligned sentence pairs produced
by the bertalign-core DP in app/services/sentence_align.py.

Why a separate table (see the phase design notes): keeping this out of
alignment_pairs leaves every existing chunk-level consumer — RAG
_attach_parallel_chunks, the unified read model, the flywheel review — untouched
and conflict-free. Sentence alignment is a distinct, finer-grained data product
(逐句对读 / cross-lingual sentence search) wired into consumers in a LATER phase.

Anchor model (mirrors alignment_pairs / text_apparatus): each side stores
(text_id, juan_num, char_start, char_end, lang) where the char offsets index
into the (text_id, juan_num, lang) row of text_contents.content — the
re-chunking-stable anchor. When the refinement job runs against a chunk-pair
whose 0168 offsets are still NULL it falls back to the chunk_text buffer, so a
minority of rows carry chunk-relative offsets until backfill_alignment_offsets
fills the parent pair; both are self-consistent per row (sent_text is the
substring at the row's own offsets).

Idempotent re-runs: uq_sentence_align on each side's leading offset lets the
refinement job INSERT ... ON CONFLICT DO NOTHING.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0170"
down_revision: str | None = "0169"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sentence_alignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Provenance: which chunk-level pair this sentence pair refined. SET NULL
        # (not CASCADE) so re-mining/deleting a chunk pair does not silently
        # destroy verified sentence pairs — they keep their own anchors.
        sa.Column(
            "source_pair_id",
            sa.Integer(),
            sa.ForeignKey("alignment_pairs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Side A anchor (offsets into text_contents(text_a_id, juan, lang).content).
        sa.Column(
            "text_a_id",
            sa.Integer(),
            sa.ForeignKey("buddhist_texts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text_a_juan_num", sa.Integer(), nullable=False),
        sa.Column("text_a_char_start", sa.Integer(), nullable=False),
        sa.Column("text_a_char_end", sa.Integer(), nullable=False),
        sa.Column("text_a_lang", sa.String(10), nullable=False),
        sa.Column("sent_a_text", sa.Text(), nullable=False),
        # Side B anchor.
        sa.Column(
            "text_b_id",
            sa.Integer(),
            sa.ForeignKey("buddhist_texts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text_b_juan_num", sa.Integer(), nullable=False),
        sa.Column("text_b_char_start", sa.Integer(), nullable=False),
        sa.Column("text_b_char_end", sa.Integer(), nullable=False),
        sa.Column("text_b_lang", sa.String(10), nullable=False),
        sa.Column("sent_b_text", sa.Text(), nullable=False),
        # Averaged cross-lingual cosine of the aligned sentence(s).
        sa.Column("similarity", sa.Float(), nullable=False),
        # '1-1' | '1-2' | '2-1' — the bertalign move that produced this pair.
        sa.Column("align_type", sa.String(8), nullable=False),
        sa.Column("method", sa.String(30), server_default="sentence-bertalign", nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # Idempotent re-runs: one row per (A leading offset, B leading offset).
        sa.UniqueConstraint(
            "text_a_id", "text_a_juan_num", "text_a_char_start",
            "text_b_id", "text_b_juan_num", "text_b_char_start",
            name="uq_sentence_align",
        ),
    )
    op.create_index("ix_sentence_align_a", "sentence_alignments", ["text_a_id", "text_a_juan_num"])
    op.create_index("ix_sentence_align_b", "sentence_alignments", ["text_b_id", "text_b_juan_num"])


def downgrade() -> None:
    op.drop_index("ix_sentence_align_b", table_name="sentence_alignments")
    op.drop_index("ix_sentence_align_a", table_name="sentence_alignments")
    # uq_sentence_align + all FKs are dropped with the table.
    op.drop_table("sentence_alignments")
