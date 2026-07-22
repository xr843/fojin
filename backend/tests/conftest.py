"""Shared fixtures for FoJin backend tests.

These tests are designed to run without external services (PG, ES, Redis).
They test pure logic: exceptions, URL building, schema validation, etc.

For integration tests (test_search_api), ES/Redis/PG are mocked.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient


def _make_mock_es(search_return=None):
    """Create a mock ES client with configurable search return value."""
    mock = AsyncMock()
    if search_return is None:
        search_return = {
            "hits": {
                "total": {"value": 0},
                "hits": [],
            },
        }
    mock.search.return_value = search_return
    mock.ping.return_value = True
    return mock


@pytest.fixture
def mock_es():
    return _make_mock_es({
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_id": "1",
                    "_score": 5.0,
                    "_source": {
                        "id": 1,
                        "cbeta_id": "T0001",
                        "title_zh": "长阿含经",
                        "source_code": "cbeta",
                    },
                    "highlight": {},
                },
                {
                    "_id": "2",
                    "_score": 3.0,
                    "_source": {
                        "id": 2,
                        "cbeta_id": "T0002",
                        "title_zh": "般若波罗蜜多心经",
                        "source_code": "cbeta",
                    },
                    "highlight": {},
                },
            ],
        },
    })


@pytest_asyncio.fixture
async def client(mock_es):
    """Async HTTP client with mocked ES (patched at each consumer module)."""
    async def mock_get_db():
        yield None

    with patch("app.api.search.get_es", return_value=mock_es), \
         patch("app.core.elasticsearch.init_es", new_callable=AsyncMock), \
         patch("app.core.elasticsearch.close_es", new_callable=AsyncMock), \
         patch("app.core.elasticsearch.get_es", return_value=mock_es), \
         patch("app.main.aioredis") as mock_redis_mod:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis_mod.from_url.return_value = mock_redis

        from app.main import app
        from app.database import get_db
        app.dependency_overrides[get_db] = mock_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def open_data_exports_enabled():
    """Mount /api/exports/* for tests that exercise the export logic.

    The routes ship unmounted (settings.enable_open_data_exports is False —
    see tests/test_open_data_exports_gate.py for why), but the code behind
    them is still live and worth covering. Monkeypatching the setting is not
    enough: routers are attached at import time, so the router has to be
    added to the app and removed again around the test.
    """
    from app.api import exports
    from app.main import app

    app.include_router(exports.router, prefix="/api")
    app.openapi_schema = None
    try:
        yield
    finally:
        app.router.routes = [r for r in app.router.routes if not getattr(r, "path", "").startswith("/api/exports")]
        app.openapi_schema = None
