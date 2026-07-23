"""Tests for the one-time OAuth code-exchange endpoint.

Verifies that the OAuth callback flow no longer puts a JWT in the
redirect URL — instead, the frontend POSTs an opaque code to
/auth/oauth/exchange to obtain the JWT.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.api.auth import OAUTH_EXCHANGE_PREFIX


@pytest.fixture(autouse=True)
def _isolate_app_state_redis():
    """Snapshot and restore ``app.state.redis`` around every test.

    The OAuth exchange endpoint reads ``request.app.state.redis``, so
    these tests have to install a mock there. Without this fixture, the
    mock leaks into subsequent tests in the same pytest session — for
    example ``tests/test_smoke.py::test_sources_include_distributions``
    starts seeing AsyncMock-returned bytes where it expects real Redis
    output, and fails with ``json.decoder.JSONDecodeError`` on the next
    HTTP response.
    """
    from app.main import app

    sentinel = object()
    original = getattr(app.state, "redis", sentinel)
    try:
        yield
    finally:
        if original is sentinel:
            if hasattr(app.state, "redis"):
                delattr(app.state, "redis")
        else:
            app.state.redis = original


def _install_redis(client, *, getdel_return=None, get_return=None):
    """Install a fresh AsyncMock as app.state.redis with deterministic behavior."""
    from app.main import app

    redis_mock = AsyncMock()
    redis_mock.getdel = AsyncMock(return_value=getdel_return)
    redis_mock.get = AsyncMock(return_value=get_return)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    app.state.redis = redis_mock
    return redis_mock


@pytest.mark.anyio
async def test_oauth_exchange_happy_path(client):
    """Valid code → returns JWT, and code is consumed (GETDEL)."""
    payload = json.dumps(
        {
            "access_token": "fake.jwt.token",
            "token_type": "bearer",
            "provider": "github",
        }
    )
    redis_mock = _install_redis(client, getdel_return=payload)

    resp = await client.post(
        "/api/auth/oauth/exchange",
        json={"code": "abcdefghijklmnopqrstuv"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "fake.jwt.token"
    assert data["token_type"] == "bearer"

    # GETDEL was called against the namespaced key — atomic single-use.
    redis_mock.getdel.assert_awaited_once_with(f"{OAUTH_EXCHANGE_PREFIX}abcdefghijklmnopqrstuv")


@pytest.mark.anyio
async def test_oauth_exchange_expired_code_returns_401(client):
    """Code not present in Redis (TTL expired or never written) → 401."""
    _install_redis(client, getdel_return=None)

    resp = await client.post(
        "/api/auth/oauth/exchange",
        json={"code": "expiredcodeabcdefghijk"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "code expired or invalid"


@pytest.mark.anyio
async def test_oauth_exchange_replay_returns_401(client):
    """Second exchange of the same code → 401 (single-use guarantee).

    Simulated by GETDEL returning the payload first, then None.
    """
    payload = json.dumps(
        {
            "access_token": "fake.jwt.token",
            "token_type": "bearer",
            "provider": "github",
        }
    )
    from app.main import app

    redis_mock = AsyncMock()
    redis_mock.getdel = AsyncMock(side_effect=[payload, None])
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    app.state.redis = redis_mock

    code = "replaytestcodeabcdefgh"

    first = await client.post("/api/auth/oauth/exchange", json={"code": code})
    assert first.status_code == 200

    second = await client.post("/api/auth/oauth/exchange", json={"code": code})
    assert second.status_code == 401
    assert second.json()["detail"] == "code expired or invalid"

    assert redis_mock.getdel.await_count == 2


@pytest.mark.anyio
async def test_oauth_exchange_malformed_code_returns_422(client):
    """Code with invalid characters or wrong length → 422 from Pydantic."""
    _install_redis(client, getdel_return=None)

    # Too short
    resp = await client.post("/api/auth/oauth/exchange", json={"code": "short"})
    assert resp.status_code == 422

    # Bad characters (spaces, punctuation)
    resp = await client.post(
        "/api/auth/oauth/exchange",
        json={"code": "has spaces and !@# chars"},
    )
    assert resp.status_code == 422

    # Empty
    resp = await client.post("/api/auth/oauth/exchange", json={"code": ""})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_oauth_exchange_corrupt_payload_returns_401(client):
    """Redis returned a non-JSON string → treat as invalid (no 500)."""
    _install_redis(client, getdel_return="not-valid-json{")

    resp = await client.post(
        "/api/auth/oauth/exchange",
        json={"code": "validlookingcode123abc"},
    )

    assert resp.status_code == 401


@pytest.mark.anyio
async def test_oauth_exchange_falls_back_when_getdel_unavailable(client):
    """Older Redis without GETDEL → fall back to GET + DELETE."""
    payload = json.dumps(
        {
            "access_token": "fake.jwt.token",
            "token_type": "bearer",
            "provider": "google",
        }
    )
    from app.main import app

    redis_mock = AsyncMock()
    # AttributeError on getdel → fallback path.
    redis_mock.getdel = AsyncMock(side_effect=AttributeError("no getdel"))
    redis_mock.get = AsyncMock(return_value=payload)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    app.state.redis = redis_mock

    resp = await client.post(
        "/api/auth/oauth/exchange",
        json={"code": "fallbackcodeabcdefghij"},
    )

    assert resp.status_code == 200
    redis_mock.get.assert_awaited_once()
    redis_mock.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_github_callback_no_longer_leaks_token_in_url(client):
    """OAuth callback redirects with ?provider=...&code=... — NOT ?token=..."""
    import app.api.auth as auth_module
    from app.main import app
    from app.schemas.user import TokenResponse

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="github")  # state matches
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    app.state.redis = redis_mock

    fake_token = TokenResponse(access_token="should.never.appear.in.url", token_type="bearer")

    original = auth_module.github_callback

    async def fake_callback(code, db):
        return fake_token

    auth_module.github_callback = fake_callback
    try:
        resp = await client.get(
            "/api/auth/github/callback",
            params={"code": "gh-oauth-code", "state": "abc123"},
            # A valid flow now also carries the state cookie set at /login;
            # without it the callback short-circuits to invalid_state and this
            # test would never reach the redirect it is actually about.
            # See tests/test_oauth_state_binding.py.
            cookies={auth_module._state_cookie_name("github"): "abc123"},
            follow_redirects=False,
        )
    finally:
        auth_module.github_callback = original

    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "token=" not in location
    assert "should.never.appear.in.url" not in location
    assert "code=" in location
    assert "provider=github" in location
