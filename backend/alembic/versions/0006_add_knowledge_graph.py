"""add kg_entities, kg_relations tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kg_entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("name_zh", sa.String(500), nullable=False),
        sa.Column("name_sa", sa.String(500), nullable=True),
        sa.Column("name_pi", sa.String(500), nullable=True),
        sa.Column("name_bo", sa.String(500), nullable=True),
        sa.Column("name_en", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("text_id", sa.Integer(), sa.ForeignKey("buddhist_texts.id"), nullable=True),
        sa.Column("external_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kg_entities_entity_type", "kg_entities", ["entity_type"])
    op.create_index("ix_kg_entities_name_zh", "kg_entities", ["name_zh"])
    op.create_index("ix_kg_entities_text_id", "kg_entities", ["text_id"])

    op.create_table(
        "kg_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("kg_entities.id"), nullable=False),
        sa.Column("predicate", sa.String(100), nullable=False),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("kg_entities.id"), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(200), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kg_relations_subject_id", "kg_relations", ["subject_id"])
    op.create_index("ix_kg_relations_object_id", "kg_relations", ["object_id"])
    op.create_index("ix_kg_relations_predicate", "kg_relations", ["predicate"])


def downgrade() -> None:
    op.drop_table("kg_relations")
    op.drop_table("kg_entities")
