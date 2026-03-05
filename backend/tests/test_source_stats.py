"""Tests for source_stats aggregated query endpoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.anyio
async def test_source_stats_returns_aggregated_data(client):
    """source_stats should return aggregated stats for each source."""
    from app.main import app
    from app.database import get_db as real_get_db

    # Mock the DB session to return aggregated row results
    mock_session = AsyncMock()

    # The endpoint now uses a single query with subquery joins
    FakeRow = type("Row", (), {
        "code": "cbeta",
        "name_zh": "CBETA",
        "name_en": "CBETA",
        "is_active": True,
        "text_count": 5000,
        "ident_count": 3000,
        "content_count": 4500,
        "char_count": 1000000,
    })
    mock_result = MagicMock()
    mock_result.all.return_value = [FakeRow()]
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[real_get_db] = lambda: mock_session
    try:
        resp = await client.get("/api/sources/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["code"] == "cbeta"
        assert data[0]["text_count"] == 5000
        assert data[0]["content_count"] == 4500
        assert data[0]["char_count"] == 1000000
    finally:
        app.dependency_overrides.pop(real_get_db, None)
