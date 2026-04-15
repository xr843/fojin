"""Extend alignment_pairs with chunk-level fields for cross-canon RAG MVP.

Revision ID: 0120
Revises: 0119

Adds chunk/juan/lang columns to alignment_pairs so we can link
text_embeddings chunks across canons (CBETA ↔ SuttaCentral ↔ 84000) without
losing the char-level segment_a/segment_b/position_a/position_b fields from
migration 0010 (kept nullable for future char-level alignment).

Also denormalizes text_a_id / text_b_id directly onto alignment_pairs so RAG
queries can look up "given this chunk, find parallel chunks" in a single
indexed table scan without joining alignment_tasks.
"""

from alembic import op
import sqlalchemy as sa


revision = "0120"
down_revision = "0119"


def upgrade() -> None:
    # Denormalize text ids from alignment_tasks onto alignment_pairs for
    # faster "given (text_id, juan, chunk) → find parallels" lookups.
    op.add_column("alignment_pairs", sa.Column("text_a_id", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_b_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_alignment_pairs_text_a", "alignment_pairs", "buddhist_texts",
        ["text_a_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_alignment_pairs_text_b", "alignment_pairs", "buddhist_texts",
        ["text_b_id"], ["id"], ondelete="CASCADE",
    )

    # Chunk-level indexing (juan + chunk_index) matching text_embeddings shape.
    op.add_column("alignment_pairs", sa.Column("text_a_juan_num", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_a_chunk_index", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_b_juan_num", sa.Integer(), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_b_chunk_index", sa.Integer(), nullable=True))

    # Language codes (lzh | pi | sa | bo | en ...) matching buddhist_texts.lang.
    op.add_column("alignment_pairs", sa.Column("text_a_lang", sa.String(10), nullable=True))
    op.add_column("alignment_pairs", sa.Column("text_b_lang", sa.String(10), nullable=True))

    # How was this pair produced: embed_llm | manual | expert | heuristic.
    op.add_column("alignment_pairs", sa.Column("method", sa.String(30), nullable=True))

    # task_id and the char-level fields become nullable: chunk-level pairs are
    # produced by the build_alignments.py script directly, not wrapped in a
    # user-owned alignment_task.
    op.alter_column("alignment_pairs", "task_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("alignment_pairs", "segment_a", existing_type=sa.Text(), nullable=True)
    op.alter_column("alignment_pairs", "segment_b", existing_type=sa.Text(), nullable=True)
    op.alter_column("alignment_pairs", "position_a", existing_type=sa.Integer(), nullable=True)
    op.alter_column("alignment_pairs", "position_b", existing_type=sa.Integer(), nullable=True)

    # Same for alignment_tasks.created_by — auto-generated tasks have no user.
    op.alter_column("alignment_tasks", "created_by", existing_type=sa.Integer(), nullable=True)

    # RAG lookup indexes: "given this chunk, what does it align to?"
    op.create_index(
        "ix_align_a_lookup",
        "alignment_pairs",
        ["text_a_id", "text_a_juan_num", "text_a_chunk_index"],
    )
    op.create_index(
        "ix_align_b_lookup",
        "alignment_pairs",
        ["text_b_id", "text_b_juan_num", "text_b_chunk_index"],
    )

    # Idempotency: don't allow duplicate (a_chunk, b_chunk) pairs.
    # Partial index on rows that have chunk indexing populated.
    op.create_index(
        "uq_align_chunk_pair",
        "alignment_pairs",
        [
            "text_a_id", "text_a_juan_num", "text_a_chunk_index",
            "text_b_id", "text_b_juan_num", "text_b_chunk_index",
        ],
        unique=True,
        postgresql_where=sa.text("text_a_chunk_index IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_align_chunk_pair", table_name="alignment_pairs")
    op.drop_index("ix_align_b_lookup", table_name="alignment_pairs")
    op.drop_index("ix_align_a_lookup", table_name="alignment_pairs")

    op.alter_column("alignment_tasks", "created_by", existing_type=sa.Integer(), nullable=False)
    op.alter_column("alignment_pairs", "position_b", existing_type=sa.Integer(), nullable=False)
    op.alter_column("alignment_pairs", "position_a", existing_type=sa.Integer(), nullable=False)
    op.alter_column("alignment_pairs", "segment_b", existing_type=sa.Text(), nullable=False)
    op.alter_column("alignment_pairs", "segment_a", existing_type=sa.Text(), nullable=False)
    op.alter_column("alignment_pairs", "task_id", existing_type=sa.Integer(), nullable=False)

    op.drop_column("alignment_pairs", "method")
    op.drop_column("alignment_pairs", "text_b_lang")
    op.drop_column("alignment_pairs", "text_a_lang")
    op.drop_column("alignment_pairs", "text_b_chunk_index")
    op.drop_column("alignment_pairs", "text_b_juan_num")
    op.drop_column("alignment_pairs", "text_a_chunk_index")
    op.drop_column("alignment_pairs", "text_a_juan_num")
    op.drop_constraint("fk_alignment_pairs_text_b", "alignment_pairs", type_="foreignkey")
    op.drop_constraint("fk_alignment_pairs_text_a", "alignment_pairs", type_="foreignkey")
    op.drop_column("alignment_pairs", "text_b_id")
    op.drop_column("alignment_pairs", "text_a_id")
