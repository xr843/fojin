"""POST /api/auth/api-key/rotate-encryption — user-driven re-encrypt."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from app.config import settings


def _user_with_key(uid=42, encrypted=None, kdf=2):
    u = MagicMock()
    u.id = uid
    u.username = "u"
    u.email = "u@example.com"
    u.role = "user"
    u.is_active = True
    u.created_at = datetime.now(UTC)
    u.encrypted_api_key = encrypted
    u.api_key_kdf_version = kdf
    u.api_provider = "openai"
    u.api_model = None
    u.api_custom_url = None
    return u


@pytest.mark.anyio
async def test_rotate_404_when_no_key(client):
    fake_user = _user_with_key(encrypted=None)
    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: AsyncMock()
    try:
        resp = await client.post("/api/auth/api-key/rotate-encryption")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_rotate_v2_to_v2_idempotent(client, monkeypatch):
    """v2 row → re-encrypt under v2 → still v2."""
    monkeypatch.setattr(
        settings, "api_key_encryption_key", Fernet.generate_key().decode()
    )
    # Build a real v2 ciphertext so decrypt actually works
    cipher = Fernet(settings.api_key_encryption_key.encode()).encrypt(b"sk-rot").decode()
    fake_user = _user_with_key(encrypted=cipher, kdf=2)

    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: AsyncMock()
    try:
        resp = await client.post("/api/auth/api-key/rotate-encryption")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["kdf_version"] == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_rotate_unauthenticated_rejected(client):
    """Codex reviewer gap: rotate must reject unauth callers."""
    resp = await client.post("/api/auth/api-key/rotate-encryption")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_rotate_409_on_undecryptable(client, monkeypatch):
    """If neither v1 nor v2 unlocks the blob, return 409 not 500."""
    monkeypatch.setattr(
        settings, "api_key_encryption_key", Fernet.generate_key().decode()
    )
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 40)
    fake_user = _user_with_key(encrypted="totally-bogus-not-a-token", kdf=2)

    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: AsyncMock()
    try:
        resp = await client.post("/api/auth/api-key/rotate-encryption")
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)
