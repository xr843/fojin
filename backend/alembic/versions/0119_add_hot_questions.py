"""Add hot_questions table for categorized welcome cards.

Revision ID: 0119
Revises: 0118
"""

from alembic import op
import sqlalchemy as sa


revision = "0119"
down_revision = "0118"


def upgrade() -> None:
    op.create_table(
        "hot_questions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("display_text", sa.String(200), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_hot_questions_slug", "hot_questions", ["slug"], unique=True)
    op.create_index("ix_hot_questions_category", "hot_questions", ["category"])
    op.create_index(
        "ix_hot_questions_category_active",
        "hot_questions",
        ["category", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_hot_questions_category_active", table_name="hot_questions")
    op.drop_index("ix_hot_questions_category", table_name="hot_questions")
    op.drop_index("ix_hot_questions_slug", table_name="hot_questions")
    op.drop_table("hot_questions")
