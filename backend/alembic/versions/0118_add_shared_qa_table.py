"""Add shared_qa table for public Q&A sharing.

Revision ID: 0118
Revises: 0117
"""

from alembic import op
import sqlalchemy as sa


revision = "0118"
down_revision = "0117"


def upgrade() -> None:
    op.create_table(
        "shared_qa",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column(
            "creator_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_shared_qa_creator_user_id",
        "shared_qa",
        ["creator_user_id"],
    )
    op.create_index(
        "ix_shared_qa_created_at",
        "shared_qa",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_shared_qa_created_at", table_name="shared_qa")
    op.drop_index("ix_shared_qa_creator_user_id", table_name="shared_qa")
    op.drop_table("shared_qa")
