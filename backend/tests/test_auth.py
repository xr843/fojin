"""Auth API tests — register, login, /me, password validation."""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import DuplicateUsernameError, DuplicateEmailError


# ---------------------------------------------------------------------------
# Helper: create a fake user object
# ---------------------------------------------------------------------------
def _fake_user(
    uid=1, username="testuser", email="test@example.com",
    role="user", is_active=True, encrypted_api_key=None,
    api_provider=None, api_model=None,
):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.email = email
    u.display_name = username
    u.role = role
    u.is_active = is_active
    u.created_at = datetime.now(timezone.utc)
    u.encrypted_api_key = encrypted_api_key
    u.api_provider = api_provider
    u.api_model = api_model
    return u


# ===========================================================================
# Registration
# ===========================================================================


@pytest.mark.anyio
async def test_register_success(client):
    """POST /auth/register with valid data returns 200 and user profile."""
    fake_user = _fake_user()

    with patch("app.api.auth.register_user", new=AsyncMock(return_value=fake_user)):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_db = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_db
        try:
            resp = await client.post("/api/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "Password1",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "testuser"
            assert data["email"] == "test@example.com"
            assert data["role"] == "user"
        finally:
            app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_register_weak_password(client):
    """POST /auth/register with weak password returns 422."""
    resp = await client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "short",
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_password_no_digit(client):
    """Password without digits should be rejected."""
    resp = await client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "NoDigitsHere",
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_password_no_letter(client):
    """Password without letters should be rejected."""
    resp = await client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "12345678",
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_invalid_email(client):
    """POST /auth/register with invalid email returns 422."""
    resp = await client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "not-an-email",
        "password": "Password1",
    })
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_register_duplicate_username(client):
    """Duplicate username should return 409."""
    with patch("app.api.auth.register_user", new=AsyncMock(side_effect=DuplicateUsernameError())):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_db = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_db
        try:
            resp = await client.post("/api/auth/register", json={
                "username": "taken",
                "email": "new@example.com",
                "password": "Password1",
            })
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_register_duplicate_email(client):
    """Duplicate email should return 409."""
    with patch("app.api.auth.register_user", new=AsyncMock(side_effect=DuplicateEmailError())):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_db = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_db
        try:
            resp = await client.post("/api/auth/register", json={
                "username": "newuser",
                "email": "taken@example.com",
                "password": "Password1",
            })
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.pop(real_get_db, None)


# ===========================================================================
# Login
# ===========================================================================


@pytest.mark.anyio
async def test_login_success(client):
    """POST /auth/login with valid credentials returns token."""
    token_resp = {"access_token": "fake.jwt.token", "token_type": "bearer"}

    with patch("app.api.auth.login_user", new=AsyncMock(return_value=token_resp)):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_db = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_db
        try:
            resp = await client.post("/api/auth/login", json={
                "username": "testuser",
                "password": "Password1",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
        finally:
            app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_login_missing_fields(client):
    """POST /auth/login without required fields returns 422."""
    resp = await client.post("/api/auth/login", json={"username": "testuser"})
    assert resp.status_code == 422


# ===========================================================================
# /me endpoint
# ===========================================================================


@pytest.mark.anyio
async def test_me_authenticated(client):
    """GET /auth/me with valid token returns user profile."""
    fake_user = _fake_user()

    from app.main import app
    from app.core.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert data["has_api_key"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_me_unauthenticated(client):
    """GET /auth/me without token returns 401."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


# ===========================================================================
# API Key management
# ===========================================================================


@pytest.mark.anyio
async def test_api_key_save(client):
    """PUT /auth/api-key should save and return status with preview."""
    fake_user = _fake_user()

    from app.main import app
    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db

    mock_db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        resp = await client.put("/api/auth/api-key", json={
            "api_key": "sk-1234567890abcdef",
            "provider": "openai",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_api_key"] is True
        assert data["provider"] == "openai"
        assert "key_preview" in data
        # Preview should mask the middle part
        assert data["key_preview"].startswith("sk-123")
        assert "..." in data["key_preview"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_api_key_delete(client):
    """DELETE /auth/api-key should clear the key."""
    fake_user = _fake_user(encrypted_api_key="encrypted_value")

    from app.main import app
    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db

    mock_db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        resp = await client.delete("/api/auth/api-key")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_api_key_unauthenticated(client):
    """API key endpoints without auth should return 401."""
    resp = await client.put("/api/auth/api-key", json={
        "api_key": "sk-test",
        "provider": "openai",
    })
    assert resp.status_code in (401, 403)
