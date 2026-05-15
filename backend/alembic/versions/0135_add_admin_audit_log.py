"""Add admin_audit_log table.

Records every state-changing admin action so role changes and account
bans/unbans are attributable. Until now ``PATCH /admin/users/{id}`` mutated
a user's role / is_active with no trace of who did it or when — a hard gap
for a user-management backend.

Why columns:

- ``actor_id`` nullable + ON DELETE SET NULL: the audit row must outlive the
  admin account; if that admin is ever deleted we keep the trail and only
  drop the link (same rationale as chat_attachments.user_id).
- ``target_type`` / ``target_id``: generic so the log can later cover
  non-user targets (sources, annotations) without a schema change.
- ``detail`` JSON: carries the before→after diff, e.g.
  {"role": {"from": "user", "to": "reviewer"}}.

Append-only: application code only ever INSERTs. Indexes mirror the read
patterns — by actor and by created_at (the audit view is time-ordered).

Revision ID: 0135
Revises: 0134
Create Date: 2026-05-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_admin_audit_log_actor_id", "admin_audit_log", ["actor_id"]
    )
    op.create_index(
        "ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_actor_id", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
