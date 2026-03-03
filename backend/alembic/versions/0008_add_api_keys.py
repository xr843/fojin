"""add api_keys, api_usage_logs tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("rate_limit", sa.Integer(), server_default="100", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    op.create_table(
        "api_usage_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_usage_logs_api_key_id", "api_usage_logs", ["api_key_id"])
    op.create_index("ix_api_usage_logs_created_at", "api_usage_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("api_usage_logs")
    op.drop_table("api_keys")
