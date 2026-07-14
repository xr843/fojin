"""Admin API tests — stats, user management, annotations, module usage."""

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


@pytest.mark.anyio
async def test_audit_log_requires_admin(client):
    """GET /admin/audit-log without auth returns 401."""
    resp = await client.get("/api/admin/audit-log")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_audit_log_non_admin(client):
    """GET /admin/audit-log as regular user returns 403."""
    fake_user = _fake_user(role="user")
    from app.main import app
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        resp = await client.get("/api/admin/audit-log")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- Module usage endpoint ---

@pytest.mark.anyio
async def test_module_usage_requires_admin(client):
    """GET /admin/stats/module-usage without auth returns 401."""
    resp = await client.get("/api/admin/stats/module-usage")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_module_usage_non_admin_forbidden(client):
    """GET /admin/stats/module-usage as regular user returns 403."""
    fake_user = _fake_user(role="user")
    from app.main import app
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        resp = await client.get("/api/admin/stats/module-usage")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_module_usage_returns_empty_on_umami_down(client):
    """Admin call should return 200 with empty lists when Umami DB is unreachable."""
    fake_admin = _fake_user(role="admin")
    from app.main import app
    from app.core.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: fake_admin
    try:
        with patch(
            "app.services.usage_service._query_module_usage",
            side_effect=Exception("connection refused"),
        ):
            resp = await client.get("/api/admin/stats/module-usage?days=7")
            assert resp.status_code == 200
            body = resp.json()
            assert body["days"] == 7
            assert body["events"] == []
            assert body["top_search_keywords"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_module_usage_returns_data(client):
    """Admin call should return properly shaped data when Umami responds."""
    fake_admin = _fake_user(role="admin")
    from app.main import app
    from app.core.deps import get_current_user

    mock_result = {
        "events": [
            {"event_name": "search", "label": "检索", "count": 42},
            {"event_name": "chat", "label": "AI问答", "count": 10},
        ],
        "top_search_keywords": [
            {"keyword": "心经", "count": 8},
        ],
        "answer_quality": {
            "chat_questions": 10,
            "citation_click": 3,
            "chat_copy": 2,
            "chat_retry": 1,
            "citation_click_rate": 30.0,
            "copy_rate": 20.0,
            "retry_rate": 10.0,
        },
    }

    app.dependency_overrides[get_current_user] = lambda: fake_admin
    try:
        with patch(
            "app.services.usage_service._query_module_usage",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.get("/api/admin/stats/module-usage?days=14")
            assert resp.status_code == 200
            body = resp.json()
            assert body["days"] == 14
            assert len(body["events"]) == 2
            assert body["events"][0]["event_name"] == "search"
            assert body["events"][0]["label"] == "检索"
            assert body["events"][0]["count"] == 42
            assert body["top_search_keywords"][0]["keyword"] == "心经"
            assert body["answer_quality"]["citation_click_rate"] == 30.0
            assert body["answer_quality"]["chat_questions"] == 10
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_module_usage_days_clamped(client):
    """days param outside 1–90 should return 422."""
    fake_admin = _fake_user(role="admin")
    from app.main import app
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_admin
    try:
        resp = await client.get("/api/admin/stats/module-usage?days=0")
        assert resp.status_code == 422
        resp2 = await client.get("/api/admin/stats/module-usage?days=91")
        assert resp2.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- Pending-summary endpoint (sidebar badge) ---

@pytest.mark.anyio
async def test_pending_summary_requires_admin(client):
    resp = await client.get("/api/admin/pending-summary")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_pending_summary_shape(client):
    """五个计数齐全 —— 角标是它的唯一消费者,少一个前端就会漏报待办。"""
    fake_admin = _fake_user(role="admin")
    from app.main import app
    from app.core.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: fake_admin
    try:
        with patch(
            "app.api.admin.count_unreviewed", new=AsyncMock(return_value=7)
        ), patch(
            "app.api.admin.count_pending_candidates", new=AsyncMock(return_value=50)
        ), patch(
            "app.api.admin.count_pending_simple", new=AsyncMock(side_effect=[4, 3, 2])
        ):
            resp = await client.get("/api/admin/pending-summary")
            assert resp.status_code == 200
            assert resp.json() == {
                "answer_quality": 7,
                "alignment_candidates": 50,
                "suggestions": 4,
                "feedbacks": 3,
                "annotations": 2,
            }
    finally:
        app.dependency_overrides.pop(get_current_user, None)
