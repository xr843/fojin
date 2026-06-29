"""add answer_reviews — admin verdicts for the bad-answer quality queue

Revision ID: 0164
Revises: 0163
Create Date: 2026-06-29

One row per assistant chat_messages row that the admin has reviewed in the
answer-quality queue. Holds the verdict (good/bad), a failure category, a free
note, and a snapshot of why the item was flagged (detection_reasons +
suspicion_score) so the labeled dataset records its own provenance. The queue
excludes any chat message already present here. Touches no existing data.

See docs/superpowers/specs/2026-06-29-answer-quality-loop-design.md.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0164"
down_revision: str | None = "0163"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answer_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=10), nullable=False),
        sa.Column("failure_category", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("detection_reasons", sa.JSON(), nullable=True),
        sa.Column("suspicion_score", sa.Float(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name="fk_answer_reviews_message",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_answer_reviews_reviewer",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("message_id", name="uq_answer_reviews_message"),
    )


def downgrade() -> None:
    op.drop_table("answer_reviews")
