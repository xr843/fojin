"""Add password_version and password_changed_at columns to users table.

Revision ID: 0117
Revises: 0116
"""

from alembic import op
import sqlalchemy as sa

revision = "0117"
down_revision = "0116"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "password_version")
