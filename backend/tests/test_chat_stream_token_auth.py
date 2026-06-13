"""Tests for the SSE-stream token auth path.

/chat/stream stopped using Depends(get_optional_user) (which pinned a PG
connection for the whole 60-120s stream via its hidden get_db dependency).
Instead it reads the raw bearer token and resolves the user INSIDE the
generator's short-lived prep session via resolve_optional_user.

These lock two things:
1. resolve_optional_user has the SAME accept/reject rules as the old
   get_optional_user (no auth regression from the extraction).
2. send_message_stream's token path resolves the user and feeds the
   resolved user_id (and the correct client_ip) into _prepare_chat.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.deps import resolve_optional_user
from app.core.exceptions import ValidationError


def _mock_db(returned_user):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=returned_user)
    db.execute = AsyncMock(return_value=result)
    return db


# ---- resolve_optional_user: auth semantics (5 branches) ----

@pytest.mark.anyio
async def test_resolve_none_token_is_anonymous():
    assert await resolve_optional_user(None, _mock_db(None)) is None
    assert await resolve_optional_user("", _mock_db(None)) is None


@pytest.mark.anyio
async def test_resolve_invalid_token_rejected():
    with patch("app.core.deps.verify_token", return_value=None):
        assert await resolve_optional_user("garbage", _mock_db(None)) is None


@pytest.mark.anyio
async def test_resolve_valid_token_returns_user():
    user = MagicMock()
    user.password_version = 3
    with patch("app.core.deps.verify_token", return_value=(7, 3)):
        result = await resolve_optional_user("good", _mock_db(user))
    assert result is user


@pytest.mark.anyio
async def test_resolve_unknown_or_disabled_user_rejected():
    # verify_token ok, but the user row is gone / inactive (query returns None)
    with patch("app.core.deps.verify_token", return_value=(7, 3)):
        assert await resolve_optional_user("good", _mock_db(None)) is None


@pytest.mark.anyio
async def test_resolve_stale_password_version_rejected():
    user = MagicMock()
    user.password_version = 5  # token was minted at version 3 -> stale
    with patch("app.core.deps.verify_token", return_value=(7, 3)):
        assert await resolve_optional_user("good", _mock_db(user)) is None


# ---- send_message_stream: token path wires resolved user into prep ----
#
# We don't mock the LLM at all: fake _prepare_chat captures what it received
# and raises ValidationError, so the generator takes its prep-error branch and
# returns before any LLM I/O. A fake sessionmaker keeps it off the real DB.

class _FakeSessionmaker:
    def __call__(self):
        class _CM:
            async def __aenter__(self_inner):
                return AsyncMock()

            async def __aexit__(self_inner, *_):
                return False

        return _CM()


async def _drain(gen):
    async for _ in gen:
        pass


@pytest.mark.anyio
async def test_stream_token_path_resolves_user_into_prepare_chat():
    """A valid token -> user resolved in prep session -> user_id to _prepare_chat."""
    from app.services import chat as chat_mod

    resolved = MagicMock()
    resolved.id = 99
    captured = {}

    async def fake_prepare(db, user_id, message, session_id, user, **kwargs):
        captured["user_id"] = user_id
        captured["user"] = user
        captured["client_ip"] = kwargs.get("client_ip")
        raise ValidationError("stop after prep — we only assert prep inputs")

    with patch.object(chat_mod, "resolve_optional_user", AsyncMock(return_value=resolved)) as mock_resolve, \
         patch.object(chat_mod, "_prepare_chat", side_effect=fake_prepare):
        await _drain(chat_mod.send_message_stream(
            None, "什么是空性？", token="valid-token", client_ip="1.2.3.4",
            sessionmaker=_FakeSessionmaker(),
        ))

    mock_resolve.assert_awaited_once()
    assert captured["user_id"] == 99
    assert captured["user"] is resolved
    # logged-in user -> client_ip must NOT be used for quota
    assert captured["client_ip"] is None


@pytest.mark.anyio
async def test_stream_anonymous_token_none_uses_client_ip():
    """No token -> resolve skipped -> anonymous, client_ip flows to prep for IP quota."""
    from app.services import chat as chat_mod

    captured = {}

    async def fake_prepare(db, user_id, message, session_id, user, **kwargs):
        captured["user_id"] = user_id
        captured["user"] = user
        captured["client_ip"] = kwargs.get("client_ip")
        raise ValidationError("stop after prep")

    with patch.object(chat_mod, "resolve_optional_user", AsyncMock(return_value=None)) as mock_resolve, \
         patch.object(chat_mod, "_prepare_chat", side_effect=fake_prepare):
        await _drain(chat_mod.send_message_stream(
            None, "什么是空性？", token=None, client_ip="5.6.7.8",
            sessionmaker=_FakeSessionmaker(),
        ))

    # token is None -> resolve must be SKIPPED entirely (no wasted query)
    mock_resolve.assert_not_awaited()
    assert captured["user_id"] is None
    assert captured["user"] is None
    assert captured["client_ip"] == "5.6.7.8"
