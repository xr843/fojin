"""Tests for password_change_audit row writing on every change attempt.

Background: a 4-12 password-change event was untraceable 25 days later
because nginx / journald / docker-logs had all rotated, and the only
DB-side trace was a single integer counter (``users.password_version``).
This test suite locks in the new contract: every change attempt writes
one row to ``password_change_audit``, capturing user_id, outcome, ip,
user_agent, and via-source.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import InvalidCredentialsError
from app.models.user import PasswordChangeAudit
from app.services.auth import change_user_password


def _fake_user(uid: int = 3, hashed: str = "hash:correct", version: int = 0):
    u = MagicMock()
    u.id = uid
    u.hashed_password = hashed
    u.password_version = version
    u.password_changed_at = None
    return u


def _capture_audit_rows(session: MagicMock) -> list[PasswordChangeAudit]:
    """Pull every PasswordChangeAudit instance handed to ``session.add``."""
    rows = []
    for call in session.add.call_args_list:
        obj = call.args[0]
        if isinstance(obj, PasswordChangeAudit):
            rows.append(obj)
    return rows


@pytest.mark.anyio
async def test_success_writes_audit_row_in_same_transaction():
    """A successful change inserts an audit row before commit, so a rollback
    on the user UPDATE would also discard the audit row (atomic)."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    user = _fake_user(version=2)

    with (
        patch("app.services.auth.verify_password", side_effect=[True, False]),
        patch("app.services.auth.hash_password", return_value="hash:new"),
        patch("app.services.auth.create_access_token", return_value="jwt"),
    ):
        resp = await change_user_password(
            session,
            user,
            old_password="old",
            new_password="new",
            client_ip="203.0.113.5",
            user_agent="curl/8",
        )

    assert resp.access_token == "jwt"
    assert user.password_version == 3
    assert user.hashed_password == "hash:new"

    rows = _capture_audit_rows(session)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.user_id == 3
    assert audit.outcome == "success"
    assert audit.via == "self"
    assert audit.ip == "203.0.113.5"
    assert audit.user_agent == "curl/8"

    # Exactly one commit at the end — the audit row rides the same
    # transaction that flips the password.
    assert session.commit.await_count == 1


@pytest.mark.anyio
async def test_wrong_old_password_writes_audit_and_does_not_change_password():
    """Failed attempt with bad old password still writes an audit row,
    so brute-force / token-leak signals are visible after the fact."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    user = _fake_user(hashed="hash:correct", version=5)

    with (
        patch("app.services.auth.verify_password", return_value=False),
        pytest.raises(InvalidCredentialsError),
    ):
        await change_user_password(
            session,
            user,
            old_password="wrong",
            new_password="anything",
            client_ip="198.51.100.7",
            user_agent="cli-tester",
        )

    # Password not flipped.
    assert user.hashed_password == "hash:correct"
    assert user.password_version == 5

    rows = _capture_audit_rows(session)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.outcome == "wrong_old_password"
    assert audit.user_id == 3
    assert audit.ip == "198.51.100.7"
    assert audit.user_agent == "cli-tester"


@pytest.mark.anyio
async def test_same_as_old_writes_audit():
    """New password == old password: writes audit row with outcome
    'same_as_old' so somebody investigating a stuck user later can
    distinguish a real attack attempt from a no-op accident."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    user = _fake_user(version=0)

    with (
        # First verify_password (old vs stored): match. Second (new vs
        # stored): also match → triggers the same-as-old branch.
        patch("app.services.auth.verify_password", side_effect=[True, True]),
        pytest.raises(InvalidCredentialsError),
    ):
        await change_user_password(session, user, old_password="x", new_password="x")

    assert user.password_version == 0
    rows = _capture_audit_rows(session)
    assert len(rows) == 1
    assert rows[0].outcome == "same_as_old"


@pytest.mark.anyio
async def test_user_agent_truncated_to_500_chars():
    """A 5KB UA from a malicious / buggy scanner must not blow up the
    INSERT (column is VARCHAR(500))."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    user = _fake_user(version=0)
    big_ua = "X" * 5000

    with (
        patch("app.services.auth.verify_password", side_effect=[True, False]),
        patch("app.services.auth.hash_password", return_value="hash:new"),
        patch("app.services.auth.create_access_token", return_value="jwt"),
    ):
        await change_user_password(
            session,
            user,
            old_password="old",
            new_password="new",
            user_agent=big_ua,
        )

    rows = _capture_audit_rows(session)
    assert len(rows) == 1
    assert rows[0].user_agent is not None
    assert len(rows[0].user_agent) == 500


@pytest.mark.anyio
async def test_via_field_defaults_to_self_and_is_overrideable():
    """``via`` defaults to 'self' (user-initiated). Allows future paths
    like 'admin_reset' / 'sms_reset' / 'oauth_first_set' to identify
    themselves without touching this service."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    user = _fake_user(version=0)

    with (
        patch("app.services.auth.verify_password", side_effect=[True, False]),
        patch("app.services.auth.hash_password", return_value="hash:new"),
        patch("app.services.auth.create_access_token", return_value="jwt"),
    ):
        await change_user_password(session, user, old_password="o", new_password="n", via="admin_reset")

    rows = _capture_audit_rows(session)
    assert len(rows) == 1
    assert rows[0].via == "admin_reset"
