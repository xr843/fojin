"""Add users.api_key_kdf_version + api_key_migration_failures table.

Part of P0-1: split the BYOK encryption key from JWT_SECRET_KEY so that
rotating the JWT secret no longer silently destroys every stored API
key.  The version column lets the read path dispatch between the legacy
KDF (v1, derived from JWT secret) and the new KDF (v2, standalone
``API_KEY_ENCRYPTION_KEY``) until ``scripts/archive/misc/migrate_api_keys.py``
re-encrypts the existing rows in place.

Backfill rules:

* Rows with ``encrypted_api_key IS NULL`` → ``api_key_kdf_version = 2``.
  No ciphertext exists, so we can claim the new version up front and the
  next BYOK save just works.
* Rows with a stored ciphertext stay at ``1`` (the column default).  The
  migrate script will pick them up and flip them to ``2`` after a
  successful re-encrypt, one row per transaction.

The companion ``api_key_migration_failures`` table records rows the
migrate script could not re-encrypt — almost always "v1 decrypt failed"
which means the stored blob was sealed with a now-rotated JWT secret
and the user must rotate their key from the UI.

Revision ID: 0130
Revises: 0129
"""

import sqlalchemy as sa
from alembic import op

revision = "0130"
down_revision = "0129"


def upgrade() -> None:
    # 1) Add the version column with a server-side default so existing
    #    rows get ``1`` automatically — matches the legacy ciphertext
    #    they're holding.
    op.add_column(
        "users",
        sa.Column(
            "api_key_kdf_version",
            sa.SmallInteger(),
            nullable=False,
            server_default="1",
        ),
    )

    # 2) Bump rows with no ciphertext to v2 directly.  They have nothing
    #    to migrate, so claiming v2 up-front means every future write
    #    goes through the new KDF without the script touching them.
    op.execute(
        sa.text(
            "UPDATE users SET api_key_kdf_version = 2 "
            "WHERE encrypted_api_key IS NULL"
        )
    )

    # 3) Failures sink for the migrate script.  Append-only; ops greps
    #    it after running the script to see which users still need to
    #    rotate their key from the UI.
    op.create_table(
        "api_key_migration_failures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        # Free-form: today either the v1 InvalidToken message or the
        # SQLAlchemy error from the per-row UPDATE.  Truncated to 500
        # chars so a runaway stack trace doesn't bloat the table.
        sa.Column("error", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("api_key_migration_failures")
    op.drop_column("users", "api_key_kdf_version")
