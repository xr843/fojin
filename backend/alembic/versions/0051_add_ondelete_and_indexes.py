"""Add ON DELETE constraints and missing indexes.

- TextContent.text_id → ON DELETE CASCADE
- BuddhistText.source_id → ON DELETE SET NULL
- Add index ix_buddhist_texts_source_id

Revision ID: 0051
Revises: 0050
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TextContent.text_id: add ON DELETE CASCADE
    op.drop_constraint(
        "text_contents_text_id_fkey", "text_contents", type_="foreignkey"
    )
    op.create_foreign_key(
        "text_contents_text_id_fkey",
        "text_contents",
        "buddhist_texts",
        ["text_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # BuddhistText.source_id: add ON DELETE SET NULL
    op.drop_constraint(
        "buddhist_texts_source_id_fkey", "buddhist_texts", type_="foreignkey"
    )
    op.create_foreign_key(
        "buddhist_texts_source_id_fkey",
        "buddhist_texts",
        "data_sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add index on buddhist_texts.source_id for join performance
    op.create_index(
        "ix_buddhist_texts_source_id", "buddhist_texts", ["source_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_buddhist_texts_source_id", table_name="buddhist_texts")

    op.drop_constraint(
        "buddhist_texts_source_id_fkey", "buddhist_texts", type_="foreignkey"
    )
    op.create_foreign_key(
        "buddhist_texts_source_id_fkey",
        "buddhist_texts",
        "data_sources",
        ["source_id"],
        ["id"],
    )

    op.drop_constraint(
        "text_contents_text_id_fkey", "text_contents", type_="foreignkey"
    )
    op.create_foreign_key(
        "text_contents_text_id_fkey",
        "text_contents",
        "buddhist_texts",
        ["text_id"],
        ["id"],
    )
