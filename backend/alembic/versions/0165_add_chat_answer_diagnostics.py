"""add chat answer diagnostics for citation trust status

Revision ID: 0165
Revises: 0164
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0165"
down_revision: str | None = "0164"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_answer_diagnostics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("trust_state", sa.String(length=30), nullable=False),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citation_mutation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quote_mutation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_source_score", sa.Float(), nullable=True),
        sa.Column("min_source_score", sa.Float(), nullable=True),
        sa.Column("citation_mutations", sa.JSON(), nullable=True),
        sa.Column("quote_mutations", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name="fk_chat_answer_diagnostics_message",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("message_id", name="uq_chat_answer_diagnostics_message"),
    )
    op.create_index(
        "ix_chat_answer_diagnostics_trust_state",
        "chat_answer_diagnostics",
        ["trust_state"],
    )
    op.create_index(
        "ix_chat_answer_diagnostics_created_at",
        "chat_answer_diagnostics",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_answer_diagnostics_created_at", table_name="chat_answer_diagnostics")
    op.drop_index("ix_chat_answer_diagnostics_trust_state", table_name="chat_answer_diagnostics")
    op.drop_table("chat_answer_diagnostics")
