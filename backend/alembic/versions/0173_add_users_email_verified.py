"""add users.email_verified and backfill from existing OAuth links

Revision ID: 0173
Revises: 0172
Create Date: 2026-07-22

Closes an account pre-hijacking hole. `register_user` accepts a self-asserted
email and the project has no email-confirmation flow, but `_find_or_create_user`
merged any social login into an existing row matching on email alone. So an
attacker could register as victim@example.com, wait for the real owner's first
Google/GitHub sign-in, and have that identity linked to the attacker-controlled
account — password included.

The merge is now gated on this column.

Backfill rationale: an address is treated as verified only if an identity
provider already vouched for it, which is exactly the set of users who have a
row in `social_accounts` with a real (non-placeholder) email. Those merges
already happened under the old code and are legitimate, so keeping them
verified preserves existing logins. Everything else — including every
password-only registration — defaults to false, which is what makes pre-claimed
addresses unusable as merge targets.

Placeholder `@noreply.fojin.app` addresses are excluded: they are synthetic
identifiers minted when a provider hides the user's email, never proven.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0173"
down_revision: str | None = "0172"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE users
           SET email_verified = true
         WHERE email NOT LIKE '%@noreply.fojin.app'
           AND EXISTS (
                 SELECT 1
                   FROM social_accounts sa
                  WHERE sa.user_id = users.id
                    AND sa.provider IN ('github', 'google')
               )
        """
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified")
