"""Admin API tests — stats, user management, annotations."""

from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_user(uid=1, username="admin", role="admin", is_active=True):
    u = MagicMock()
    u.id = uid
    u.username = username
    u.email = f"{username}@example.com"
    u.display_name = username
    u.role = role
    u.is_active = is_active
    u.created_at = datetime.now(timezone.utc)
    u.updated_at = datetime.now(timezone.utc)
    u.last_active_at = datetime.now(timezone.utc)
    return u


@pytest.mark.anyio
async def test_stats_overview_requires_admin(client):
    """GET /admin/stats/overview without auth returns 401."""
    resp = await client.get("/api/admin/stats/overview")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_stats_overview_non_admin(client):
    """GET /admin/stats/overview as regular user returns 403."""
    fake_user = _fake_user(role="user")
    from app.main import app
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        resp = await client.get("/api/admin/stats/overview")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_users_list_requires_admin(client):
    """GET /admin/users without auth returns 401."""
    resp = await client.get("/api/admin/users")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_user_update_cannot_self_modify(client):
    """PATCH /admin/users/{self_id} should return 400."""
    fake_admin = _fake_user(uid=1, role="admin")
    from app.main import app
    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db

    mock_db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: fake_admin
    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        resp = await client.patch("/api/admin/users/1", json={"role": "user"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_annotations_list_requires_admin(client):
    """GET /admin/annotations without auth returns 401."""
    resp = await client.get("/api/admin/annotations")
    assert resp.status_code in (401, 403)
