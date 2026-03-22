"""Tests for stats API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from app.core.dynasty_config import resolve_dynasty, get_year_range


def test_resolve_dynasty_direct():
    d = resolve_dynasty("唐")
    assert d is not None
    assert d["key"] == "tang"
    assert d["start"] == 618


def test_resolve_dynasty_alias():
    d = resolve_dynasty("姚秦")
    assert d is not None
    assert d["name_zh"] == "十六國"


def test_resolve_dynasty_none():
    assert resolve_dynasty(None) is None
    assert resolve_dynasty("不存在") is None


def test_get_year_range():
    r = get_year_range("唐")
    assert r == (618, 907)


def test_get_year_range_none():
    assert get_year_range("不存在") is None


_FAKE_OVERVIEW = {
    "summary": {"total_texts": 100, "total_sources": 10},
    "dynasty_distribution": [],
    "language_distribution": [],
    "category_distribution": [],
    "source_coverage": [],
    "top_translators": [],
    "translation_trend": [],
}


@pytest.mark.anyio
async def test_stats_overview(client):
    with patch("app.api.stats.get_overview", new=AsyncMock(return_value=_FAKE_OVERVIEW)):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_db = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_db
        try:
            resp = await client.get("/api/stats/overview")
            assert resp.status_code == 200
            data = resp.json()
            assert "summary" in data
            assert "dynasty_distribution" in data
            assert "language_distribution" in data
            assert "category_distribution" in data
            assert "top_translators" in data
        finally:
            app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_stats_timeline_texts(client):
    fake_timeline = {"items": [], "total": 0}
    with patch("app.api.stats.get_timeline", new=AsyncMock(return_value=fake_timeline)):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_db = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_db
        try:
            resp = await client.get("/api/stats/timeline", params={"dimension": "texts"})
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
        finally:
            app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_stats_timeline_invalid_dimension(client):
    resp = await client.get("/api/stats/timeline", params={"dimension": "invalid"})
    assert resp.status_code == 422
