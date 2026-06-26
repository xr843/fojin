"""add term_concepts + term_concept_entries for the cross-lingual term layer

Revision ID: 0160
Revises: 0159
Create Date: 2026-06-26

A concept layer that links the same Buddhist term across the dictionary corpus's
languages (中梵巴藏…). ``term_concepts`` is keyed by a normalized Sanskrit-IAST
string with per-language representative forms denormalized for fast rendering;
``term_concept_entries`` is the M:N link from a concept to the actual
``dictionary_entries`` rows.

Both tables are created empty; population is offline via
``scripts/build_term_concepts.py`` (parses Mahāvyutpatti / 四譯合璧 structured
definitions + romanized-headword joins). This migration touches no existing data.
See docs/superpowers/specs/2026-06-26-dict-term-concepts-design.md.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0160"
down_revision: str | None = "0159"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "term_concepts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("sanskrit", sa.String(length=200), nullable=True),
        sa.Column("devanagari", sa.String(length=200), nullable=True),
        sa.Column("pali", sa.String(length=200), nullable=True),
        sa.Column("tibetan", sa.String(length=300), nullable=True),
        sa.Column("chinese", sa.String(length=200), nullable=True),
        sa.Column("english", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_term_concepts_key", "term_concepts", ["key"], unique=True)
    op.create_index("ix_term_concepts_chinese", "term_concepts", ["chinese"])

    op.create_table(
        "term_concept_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("concept_id", sa.Integer(), nullable=False),
        sa.Column("dict_entry_id", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=10), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=False, server_default="high"),
        sa.ForeignKeyConstraint(
            ["concept_id"], ["term_concepts.id"], name="fk_tce_concept", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dict_entry_id"],
            ["dictionary_entries.id"],
            name="fk_tce_entry",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("concept_id", "dict_entry_id", name="uq_term_concept_entry"),
    )
    op.create_index("ix_tce_concept", "term_concept_entries", ["concept_id"])
    op.create_index("ix_tce_entry", "term_concept_entries", ["dict_entry_id"])


def downgrade() -> None:
    op.drop_index("ix_tce_entry", table_name="term_concept_entries")
    op.drop_index("ix_tce_concept", table_name="term_concept_entries")
    op.drop_table("term_concept_entries")
    op.drop_index("ix_term_concepts_chinese", table_name="term_concepts")
    op.drop_index("ix_term_concepts_key", table_name="term_concepts")
    op.drop_table("term_concepts")
