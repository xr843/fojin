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
def exports_app():
    """A dedicated app carrying only the open-data export routes.

    The routes ship unmounted (settings.enable_open_data_exports is False —
    see tests/test_open_data_exports_gate.py for why), but the code behind
    them is still live and worth covering.

    Deliberately NOT mounted onto the shared `app.main.app` singleton and
    unmounted afterwards: that is order-dependent, and a teardown that does
    not run leaks the routes into the gate tests, which then hit the real
    handlers with the suite's `get_db` override (which yields None) or fall
    through to a real database connection. Giving the exports their own app
    makes that class of bug impossible rather than merely unlikely.
    """
    from fastapi import FastAPI

    from app.api import exports
    from app.database import get_db

    async def mock_get_db():
        yield None

    test_app = FastAPI()
    test_app.include_router(exports.router, prefix="/api")
    test_app.dependency_overrides[get_db] = mock_get_db
    return test_app


@pytest_asyncio.fixture
async def exports_client(exports_app):
    """HTTP client bound to `exports_app`."""
    transport = ASGITransport(app=exports_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
