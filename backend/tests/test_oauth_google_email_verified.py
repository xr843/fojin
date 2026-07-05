"""Google OAuth must not trust an unverified email for account matching.

_find_or_create_user links a social login to any existing user with the same
email. If the Google userinfo email is unverified, honoring it would let a
caller asserting someone else's address take over that account. These tests
pin that only ``email_verified`` emails are used for merging.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _FakeGoogleClient:
    """Stands in for httpx.AsyncClient: token POST then userinfo GET."""

    def __init__(self, userinfo):
        self._userinfo = userinfo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        return _FakeResp({"access_token": "ya29.fake"})

    async def get(self, url, **kwargs):
        return _FakeResp(self._userinfo)


def _patch(monkeypatch, userinfo):
    from app.services import oauth

    captured = {}

    async def fake_find_or_create(db, **kwargs):
        captured.update(kwargs)
        user = MagicMock()
        user.id = 1
        user.password_version = 0
        return user

    monkeypatch.setattr(oauth, "_find_or_create_user", fake_find_or_create)
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda *a, **k: _FakeGoogleClient(userinfo))
    return oauth, captured


@pytest.mark.anyio
async def test_verified_email_is_used_for_matching(monkeypatch):
    oauth, captured = _patch(
        monkeypatch,
        {"sub": "g-1", "email": "user@example.com", "email_verified": True, "name": "U"},
    )
    await oauth.google_callback("code", AsyncMock())
    assert captured["email"] == "user@example.com"


@pytest.mark.anyio
async def test_verified_email_as_string_true_is_accepted(monkeypatch):
    # Some Google responses serialize the flag as the string "true".
    oauth, captured = _patch(
        monkeypatch,
        {"sub": "g-1", "email": "user@example.com", "email_verified": "true", "name": "U"},
    )
    await oauth.google_callback("code", AsyncMock())
    assert captured["email"] == "user@example.com"


@pytest.mark.anyio
async def test_unverified_email_is_dropped(monkeypatch):
    oauth, captured = _patch(
        monkeypatch,
        {"sub": "g-1", "email": "victim@example.com", "email_verified": False, "name": "A"},
    )
    await oauth.google_callback("code", AsyncMock())
    assert captured["email"] is None


@pytest.mark.anyio
async def test_missing_email_verified_is_dropped(monkeypatch):
    oauth, captured = _patch(
        monkeypatch,
        {"sub": "g-1", "email": "victim@example.com", "name": "A"},
    )
    await oauth.google_callback("code", AsyncMock())
    assert captured["email"] is None
