"""add works, work_witnesses, work_aliases (FRBR Work spine)

Revision ID: 0145
Revises: 0144
Create Date: 2026-05-30

Pure additive: introduces a Work layer above buddhist_texts to aggregate
cross-language / cross-canon witnesses of the same work. Does NOT touch
buddhist_texts / text_identifiers / alignment_pairs. Zero-downtime,
reversible. Backfill is handled out-of-band by scripts/build_works.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0145"
down_revision: str | None = "0144"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "works",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("title_primary", sa.String(500), nullable=False),
        sa.Column("title_sa", sa.String(500), nullable=True),
        sa.Column("title_pi", sa.String(500), nullable=True),
        sa.Column("sc_root_uid", sa.String(200), nullable=True),
        sa.Column("toh_number", sa.String(50), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_works_slug", "works", ["slug"], unique=True)
    op.create_index("ix_works_title_primary", "works", ["title_primary"])
    op.create_index("ix_works_title_sa", "works", ["title_sa"])
    op.create_index("ix_works_sc_root_uid", "works", ["sc_root_uid"])
    op.create_index("ix_works_toh_number", "works", ["toh_number"])

    op.create_table(
        "work_witnesses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "work_id",
            sa.Integer(),
            sa.ForeignKey("works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "text_id",
            sa.Integer(),
            sa.ForeignKey("buddhist_texts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), server_default="translation", nullable=False),
        sa.Column("lang", sa.String(10), nullable=False),
        sa.Column("canon", sa.String(50), nullable=True),
        sa.Column("confidence", sa.String(20), server_default="auto", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_id", "text_id", name="uq_work_witness_work_text"),
    )
    op.create_index("ix_work_witnesses_work_id", "work_witnesses", ["work_id"])
    op.create_index("ix_work_witnesses_text_id", "work_witnesses", ["text_id"])

    op.create_table(
        "work_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "work_id",
            sa.Integer(),
            sa.ForeignKey("works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheme", sa.String(50), nullable=False),
        sa.Column("value", sa.String(300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme", "value", name="uq_work_alias_scheme_value"),
    )
    op.create_index("ix_work_aliases_work_id", "work_aliases", ["work_id"])


def downgrade() -> None:
    op.drop_table("work_aliases")
    op.drop_table("work_witnesses")
    op.drop_table("works")
