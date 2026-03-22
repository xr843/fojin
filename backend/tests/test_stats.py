"""Tests for stats API endpoints."""

import pytest

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


@pytest.mark.asyncio
async def test_stats_overview(client):
    resp = await client.get("/api/stats/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "dynasty_distribution" in data
    assert "language_distribution" in data
    assert "category_distribution" in data
    assert "top_translators" in data


@pytest.mark.asyncio
async def test_stats_timeline_texts(client):
    resp = await client.get("/api/stats/timeline", params={"dimension": "texts"})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_stats_timeline_invalid_dimension(client):
    resp = await client.get("/api/stats/timeline", params={"dimension": "invalid"})
    assert resp.status_code == 422
