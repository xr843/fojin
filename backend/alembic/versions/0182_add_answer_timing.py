"""add answer timing to chat_answer_diagnostics

Revision ID: 0182
Revises: 0181
Create Date: 2026-10-13

Per-answer latency was not recorded anywhere: the frontend shows 首字/总耗时 but
never persists them, the backend only logs TIMING lines, and container logs
rotate at 3×10MB (~10 hours of history). So "did answers get slower?" — e.g. to
explain why heavy users asked a third fewer questions in Sep–Oct — could not be
answered at all.

Columns (all nullable, no server_default: NULL = "not recorded", which is every
row written before this migration and every non-stream answer):
- prep_ms        request start → retrieval/prompt prep finished
- first_token_ms request start → first visible answer character
- total_ms       request start → stream finished (before persistence)
- model          the model that actually served the answer (the fallback model
                 when the primary failed), not the one requested
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0182"
down_revision: str | None = "0181"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_answer_diagnostics", sa.Column("prep_ms", sa.Integer(), nullable=True))
    op.add_column("chat_answer_diagnostics", sa.Column("first_token_ms", sa.Integer(), nullable=True))
    op.add_column("chat_answer_diagnostics", sa.Column("total_ms", sa.Integer(), nullable=True))
    op.add_column("chat_answer_diagnostics", sa.Column("model", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_answer_diagnostics", "model")
    op.drop_column("chat_answer_diagnostics", "total_ms")
    op.drop_column("chat_answer_diagnostics", "first_token_ms")
    op.drop_column("chat_answer_diagnostics", "prep_ms")
