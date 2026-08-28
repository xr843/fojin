"""Session lifetime: how long a sign-in survives, and how to end it early.

Background (measured on prod, 90 days, 159 signed-in users): with an 8-hour
JWT and no refresh token, 42% of returns landed on a dead token and 45% of
users were logged out at least once — 400 of those returns were in the 8-24h
band, i.e. "came back the next evening". Sliding renewal (#1198) only extends a
token that is still alive, so it never covered an overnight gap.

These tests pin the two halves of the fix: the idle budget is now days rather
than hours, and there is a way to revoke every outstanding token without
changing your password.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.core.auth import create_access_token, decode_token_claims
from app.models.user import PasswordChangeAudit
from app.services.auth import revoke_all_sessions


def _fake_user(uid: int = 7, version: int = 4):
    u = MagicMock()
    u.id = uid
    u.password_version = version
    u.password_changed_at = "untouched"
    u.hashed_password = "hash:unchanged"
    return u


def test_fresh_token_survives_an_overnight_gap():
    """The case that produced 400 forced re-logins: away all night, back tomorrow.

    Renewal cannot help here — it only fires on a request made while the token
    is still valid — so the raw lifetime has to cover the gap on its own.
    """
    claims = decode_token_claims(create_access_token(1, 0))
    assert claims is not None
    remaining = datetime.fromtimestamp(claims["exp"], UTC) - datetime.now(UTC)
    assert remaining > timedelta(hours=24)


def test_idle_budget_is_thirty_days():
    assert settings.jwt_expire_minutes == 60 * 24 * 30


def test_absolute_cap_outlives_the_idle_budget():
    """A cap shorter than the token's life would make renewal unreachable.

    ``should_renew`` only fires in the token's second half, so a cap below
    1.5x the lifetime would expire the session before it could ever renew —
    silently turning the absolute cap into the effective lifetime.
    """
    assert timedelta(days=settings.jwt_absolute_max_days) > timedelta(
        minutes=settings.jwt_expire_minutes
    ) * 1.5


@pytest.mark.anyio
async def test_revoke_all_sessions_bumps_version_and_returns_a_live_token():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    user = _fake_user(version=4)

    with patch("app.services.auth.create_access_token", return_value="jwt:new") as mint:
        resp = await revoke_all_sessions(session, user, client_ip="203.0.113.9", user_agent="curl/8")

    # Every outstanding token now mismatches on pwd_v and 401s...
    assert user.password_version == 5
    # ...except the caller's, which is re-minted at the new version.
    assert resp.access_token == "jwt:new"
    mint.assert_called_once_with(7, 5)


@pytest.mark.anyio
async def test_revoke_all_sessions_leaves_the_password_alone():
    """It is a sign-out, not a password change: only the version moves."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    user = _fake_user()

    with patch("app.services.auth.create_access_token", return_value="jwt"):
        await revoke_all_sessions(session, user)

    assert user.hashed_password == "hash:unchanged"
    assert user.password_changed_at == "untouched"


@pytest.mark.anyio
async def test_revoke_all_sessions_is_audited_in_the_same_transaction():
    """Every reason password_version moves has to land in one table, or the
    forensic question "why did this user's tokens all die?" has no answer."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    user = _fake_user()

    with patch("app.services.auth.create_access_token", return_value="jwt"):
        await revoke_all_sessions(session, user, client_ip="198.51.100.2", user_agent="ua")

    rows = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], PasswordChangeAudit)]
    assert len(rows) == 1
    assert rows[0].outcome == "revoke_all_sessions"
    assert rows[0].ip == "198.51.100.2"
    assert rows[0].user_agent == "ua"
    assert len(rows[0].outcome) <= 40  # column width
    # One commit: the audit row rides the same transaction as the bump.
    assert session.commit.await_count == 1
