"""Add password_change_audit table.

The 4-12 incident showed that ``users.password_version`` (a counter) is
not enough to investigate a "who changed this password?" event 25 days
after the fact. The original surface was the API endpoint and a docker
exec session, but the only persisted evidence was a single integer that
had advanced; nginx access logs, journalctl, and docker logs had all
rotated.

This table records every attempt — success and failure — so the next
"mystery" event can be traced from the database alone.

Revision ID: 0127
Revises: 0126
"""

import sqlalchemy as sa
from alembic import op

revision = "0127"
down_revision = "0126"


def upgrade() -> None:
    op.create_table(
        "password_change_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # 'success' | 'wrong_old_password' | 'same_as_old' — VARCHAR rather
        # than ENUM so future outcomes ('admin_reset', 'expired_token') can
        # be added without a migration.
        sa.Column("outcome", sa.String(40), nullable=False),
        # Provenance: today only 'self' (user-initiated via /api/auth/
        # change-password). Reserved values: 'admin_reset', 'sms_reset',
        # 'oauth_first_set'.
        sa.Column("via", sa.String(20), nullable=False, server_default="self"),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
    )
    # Hot lookup: "show me all change attempts for user X, newest first".
    op.create_index(
        "ix_password_change_audit_user_changed_at",
        "password_change_audit",
        ["user_id", sa.text("changed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_change_audit_user_changed_at",
        table_name="password_change_audit",
    )
    op.drop_table("password_change_audit")
