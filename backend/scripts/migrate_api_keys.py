"""One-shot v1→v2 BYOK key migration.

Usage::

    python -m scripts.migrate_api_keys --dry-run          # list candidates
    python -m scripts.migrate_api_keys                    # execute
    python -m scripts.migrate_api_keys --notify-admin-on-fail

The script is intentionally **not** wired into a startup hook.  It runs
once after deploy, prints a summary, and exits.  Re-running it after
success is a no-op (the WHERE clause filters out v2 rows).

Failure handling
----------------

A row that can't be re-encrypted (almost always: legacy v1 ciphertext
sealed with a JWT secret that has since been rotated) is logged into
``api_key_migration_failures`` so ops has a single place to grep.  The
user must rotate their key from the UI — see ``POST /api/auth/api-key/
rotate-encryption``.

The ``--notify-admin-on-fail`` flag is reserved for future hookup to
fojin's notification channel.  Today it just emits a summary line at the
end; there's no built-in admin email path in the project yet.  TODO is
tracked in the PR description.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# scripts/ is run as a top-level package (``python -m scripts.X``); fix
# sys.path so ``from app...`` resolves whether invoked from /app/backend
# inside the container or from a checkout on the host.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.crypto import (
    KDF_VERSION_V1,
    KDF_VERSION_V2,
    _get_v1_fernet,
    encrypt_api_key,
)

logger = logging.getLogger("migrate_api_keys")


CANDIDATE_SQL = text(
    "SELECT id, encrypted_api_key FROM users "
    "WHERE api_key_kdf_version = :v AND encrypted_api_key IS NOT NULL "
    "ORDER BY id"
)


async def _list_candidates(session: AsyncSession) -> list[tuple[int, str]]:
    rows = await session.execute(CANDIDATE_SQL, {"v": KDF_VERSION_V1})
    return [(r.id, r.encrypted_api_key) for r in rows]


async def _migrate_one(session: AsyncSession, user_id: int, v1_blob: str) -> tuple[bool, str]:
    """Return ``(ok, error_message)``.  Each row is its own transaction
    so a single bad blob doesn't poison the rest."""
    try:
        plaintext = _get_v1_fernet().decrypt(v1_blob.encode()).decode()
    except Exception as exc:  # InvalidToken or anything else
        return False, f"v1 decrypt failed: {exc.__class__.__name__}: {exc}"

    try:
        new_cipher, _ = encrypt_api_key(plaintext)
    except Exception as exc:
        return False, f"v2 encrypt failed: {exc.__class__.__name__}: {exc}"

    try:
        await session.execute(
            text(
                "UPDATE users SET encrypted_api_key = :c, api_key_kdf_version = :v "
                "WHERE id = :id AND api_key_kdf_version = :v1"
            ),
            {
                "c": new_cipher,
                "v": KDF_VERSION_V2,
                "id": user_id,
                "v1": KDF_VERSION_V1,
            },
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        return False, f"UPDATE failed: {exc.__class__.__name__}: {exc}"
    return True, ""


async def _record_failure(session: AsyncSession, user_id: int, error: str) -> None:
    """Append a failure row, but at most once per user_id per failing
    migration window.  Codex review flagged that re-running the script
    after a partial failure would otherwise spam the audit table; ops
    cares about the *current* set of unmigrated users, not a per-run
    counter.  We dedupe at insert time rather than via a unique index
    so the column can carry distinct error messages over the lifetime
    of the system (e.g. v1 decrypt failure today, then a different
    error after JWT_SECRET rotation tomorrow)."""
    truncated = error[:500]
    await session.execute(
        text(
            "INSERT INTO api_key_migration_failures (user_id, error) "
            "SELECT :uid, :err "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM api_key_migration_failures "
            "  WHERE user_id = :uid AND error = :err"
            ")"
        ),
        {"uid": user_id, "err": truncated},
    )
    await session.commit()


async def run(dry_run: bool, notify_admin_on_fail: bool) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    # Hard refusal: without API_KEY_ENCRYPTION_KEY explicitly set in the
    # process env, app/config.py's dev fallback would synthesize an
    # ephemeral key.  Re-encrypting prod ciphertexts under a process-
    # local random key and committing them is exactly the data-loss
    # scenario this migration exists to prevent.  Fail loudly before we
    # touch any rows.
    if not os.environ.get("API_KEY_ENCRYPTION_KEY"):
        logger.error(
            "API_KEY_ENCRYPTION_KEY is not set in the process environment. "
            "Refusing to run — re-encrypting under an ephemeral dev key "
            "would corrupt every migrated row on the next restart."
        )
        return 2

    engine = create_async_engine(settings.database_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        candidates = await _list_candidates(session)

    if not candidates:
        logger.info("No v1 rows to migrate — nothing to do.")
        await engine.dispose()
        return 0

    logger.info("Found %d v1 row(s) to migrate.", len(candidates))
    if dry_run:
        for uid, _ in candidates:
            logger.info("  would migrate user_id=%s", uid)
        await engine.dispose()
        return 0

    succeeded = 0
    failed: list[tuple[int, str]] = []
    for uid, blob in candidates:
        async with Session() as session:
            ok, err = await _migrate_one(session, uid, blob)
        if ok:
            succeeded += 1
            logger.info("  user_id=%s migrated v1 → v2", uid)
        else:
            failed.append((uid, err))
            logger.error("  user_id=%s FAILED: %s", uid, err)
            async with Session() as session:
                try:
                    await _record_failure(session, uid, err)
                except Exception as exc:
                    # Don't crash the whole run because the audit insert
                    # failed — the error log above is the source of truth.
                    logger.error("  user_id=%s failure-record insert failed: %s", uid, exc)

    logger.info("=== migration summary ===")
    logger.info("succeeded: %d", succeeded)
    logger.info("failed:    %d", len(failed))
    if failed and notify_admin_on_fail:
        # Hookup to a real admin notification channel is a TODO — fojin
        # doesn't have one yet.  Emit a clearly-tagged log line that ops
        # can scrape.
        logger.warning(
            "ADMIN_NOTIFY: %d API key migration failure(s); "
            "see api_key_migration_failures table",
            len(failed),
        )

    await engine.dispose()
    # Exit 0 even on partial failure — the failures are durably recorded
    # and a non-zero exit would just confuse a single-shot deploy step.
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List rows that would be migrated; make no changes.",
    )
    parser.add_argument(
        "--notify-admin-on-fail",
        action="store_true",
        help="Emit an ADMIN_NOTIFY log line if any rows fail (placeholder for real channel).",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.dry_run, args.notify_admin_on_fail)))


if __name__ == "__main__":
    main()
