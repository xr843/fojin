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

Backfill rationale: an address counts as verified only where an identity
provider actually vouched for it. The obvious predicate — "has a github/google
social_accounts row" — is too loose, because a *successful* pre-hijack looks
exactly like that: the attacker's password row acquires the victim's social
link. Marking those verified would bless the compromise permanently and make
that row a valid merge target for every future provider. `provider_data` stores
only login/avatar, never the email, so the address itself can't be re-checked.

The discriminator is timing. `_find_or_create_user` inserts the user and its
social row in one transaction, so an OAuth-created account has effectively
identical `created_at` values; a password account that later absorbed a social
identity has a visible gap. On production the split is clean: 113 of 120
candidate rows have a sub-5-second gap, and the 7 with a gap span 50 seconds to
41 days.

Those 7 stay `false`. That does not break them — an existing social link
short-circuits on the `social_accounts` lookup before email is ever consulted,
so they sign in exactly as before. They only lose auto-merge of a *future,
not-yet-linked* provider, which would give them a second account. That is the
right side to err on for a fix whose whole purpose is to stop unverified
addresses being merge targets.

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
                    AND sa.created_at <= users.created_at + interval '5 seconds'
               )
        """
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified")
