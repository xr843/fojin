"""Tests for search API endpoints using mocked Elasticsearch."""

import pytest


@pytest.mark.asyncio
async def test_search_returns_results(client):
    resp = await client.get("/api/search", params={"q": "阿含"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["cbeta_id"] == "T0001"


@pytest.mark.asyncio
async def test_search_empty_query(client):
    resp = await client.get("/api/search", params={"q": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data


@pytest.mark.asyncio
async def test_search_pagination_params(client):
    resp = await client.get("/api/search", params={"q": "般若", "page": 1, "size": 10})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
