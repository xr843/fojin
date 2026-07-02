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


@pytest.mark.asyncio
async def test_version_endpoint_reports_deploy_identity(client, monkeypatch):
    monkeypatch.setenv("FOJIN_COMMIT_SHA", "abcdef1234567890")
    monkeypatch.setenv("APP_VERSION", "2026.07.02")

    resp = await client.get("/api/version")

    assert resp.status_code == 200
    assert resp.json() == {
        "app": "fojin",
        "version": "2026.07.02",
        "commit": "abcdef1234567890",
        "commit_short": "abcdef1",
    }


@pytest.mark.asyncio
async def test_health_endpoint_includes_deploy_identity(client, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "1234567890abcdef")
    monkeypatch.delenv("FOJIN_COMMIT_SHA", raising=False)

    resp = await client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json()["version"]["commit"] == "1234567890abcdef"
    assert resp.json()["version"]["commit_short"] == "1234567"
