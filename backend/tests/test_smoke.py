"""Smoke tests for critical API endpoints."""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Test 1: /api/search?q=般若&sources=cbeta passes source filter to ES
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_with_sources_filter(client, mock_es):
    """Search with sources parameter should pass terms filter to ES."""
    resp = await client.get("/api/search", params={"q": "般若", "sources": "cbeta"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "results" in data

    # Verify the *first* ES search call has the source_code filter
    # (subsequent calls may be the phrase-suggestion query)
    call_args = mock_es.search.call_args_list[0]
    body = call_args.kwargs.get("body") or call_args[1].get("body")
    filters = body["query"]["bool"]["filter"]
    source_filter = [f for f in filters if "term" in f or "terms" in f]
    assert len(source_filter) > 0, "sources filter not passed to ES"
    # Verify the filter value is correct
    sf = source_filter[0]
    if "term" in sf:
        assert sf["term"]["source_code"] == "cbeta"
    else:
        assert "cbeta" in sf["terms"]["source_code"]


# ---------------------------------------------------------------------------
# Test 2: /api/search total count is purely from ES hits
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_total_is_local_only(client, mock_es):
    """Search response total should reflect only ES hit count."""
    mock_es.search.return_value = {
        "hits": {
            "total": {"value": 42},
            "hits": [],
        },
    }
    resp = await client.get("/api/search", params={"q": "般若"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 42, "Total should match ES hit count exactly"


# ---------------------------------------------------------------------------
# Test 3: /api/sources returns seeded distribution endpoints in response model
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_sources_include_distributions(client):
    """Sources response should include nested distribution metadata."""
    fake_dist = MagicMock()
    fake_dist.id = 1
    fake_dist.code = "cbeta-xml-p5"
    fake_dist.name = "CBETA XML P5"
    fake_dist.channel_type = "git"
    fake_dist.url = "https://github.com/cbeta-org/xml-p5"
    fake_dist.format = "xml"
    fake_dist.license_note = "Primary ingest"
    fake_dist.is_primary_ingest = True
    fake_dist.priority = 10
    fake_dist.is_active = True
    fake_dist.created_at = datetime.now(timezone.utc)

    fake_source = MagicMock()
    fake_source.id = 1
    fake_source.code = "cbeta"
    fake_source.name_zh = "CBETA 中华电子佛典"
    fake_source.name_en = "CBETA"
    fake_source.base_url = "https://cbetaonline.dila.edu.tw"
    fake_source.api_url = None
    fake_source.description = "test"
    fake_source.access_type = "local"
    fake_source.region = "中国台湾"
    fake_source.languages = "lzh"
    fake_source.supports_search = True
    fake_source.supports_fulltext = True
    fake_source.has_local_fulltext = True
    fake_source.has_remote_fulltext = False
    fake_source.supports_iiif = False
    fake_source.supports_api = True
    fake_source.is_active = True
    fake_source.created_at = datetime.now(timezone.utc)
    fake_source.distributions = [fake_dist]

    mock_session = AsyncMock()

    with patch("app.api.sources.get_all_sources", new=AsyncMock(return_value=[fake_source])):
        from app.main import app
        from app.database import get_db as real_get_db

        app.dependency_overrides[real_get_db] = lambda: mock_session
        try:
            resp = await client.get("/api/sources")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["code"] == "cbeta"
            assert data[0]["distributions"][0]["code"] == "cbeta-xml-p5"
            assert data[0]["distributions"][0]["is_primary_ingest"] is True
        finally:
            app.dependency_overrides.pop(real_get_db, None)


# ---------------------------------------------------------------------------
# Test 4: /api/sources/ingest/primary returns flattened primary ingest endpoints
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_primary_ingest_distributions_endpoint(client):
    """Primary ingest endpoint should expose flattened source metadata."""
    fake_source = MagicMock()
    fake_source.code = "cbeta"
    fake_source.name_zh = "CBETA 中华电子佛典"

    fake_dist = MagicMock()
    fake_dist.id = 1
    fake_dist.source_id = 1
    fake_dist.source = fake_source
    fake_dist.code = "cbeta-xml-p5"
    fake_dist.name = "CBETA XML P5"
    fake_dist.channel_type = "git"
    fake_dist.url = "https://github.com/cbeta-org/xml-p5"
    fake_dist.format = "xml"
    fake_dist.license_note = "Primary ingest"
    fake_dist.is_primary_ingest = True
    fake_dist.priority = 10
    fake_dist.is_active = True
    fake_dist.created_at = datetime.now(timezone.utc)

    with patch(
        "app.api.sources.get_primary_ingest_distributions",
        new=AsyncMock(return_value=[fake_dist]),
    ):
        from app.main import app
        from app.database import get_db as real_get_db

        mock_session = AsyncMock()
        app.dependency_overrides[real_get_db] = lambda: mock_session
        try:
            resp = await client.get("/api/sources/ingest/primary")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["source_code"] == "cbeta"
            assert data[0]["source_name"] == "CBETA 中华电子佛典"
            assert data[0]["code"] == "cbeta-xml-p5"
        finally:
            app.dependency_overrides.pop(real_get_db, None)


# ===========================================================================
# Chat / AI Q&A permission tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 5: POST /chat with someone else's session_id is rejected
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_chat_rejects_foreign_session(client):
    """POST /chat with a session_id owned by another user should return 403."""
    # Create a fake session owned by user 999
    fake_session = MagicMock()
    fake_session.id = 42
    fake_session.user_id = 999

    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "testuser"
    fake_user.is_active = True

    from app.main import app
    from app.core.deps import get_current_user, get_optional_user
    from app.database import get_db as real_get_db

    mock_session = AsyncMock()
    # Simulate get_session() finding the foreign session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_session
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_optional_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: mock_session
    try:
        resp = await client.post("/api/chat", json={"message": "test", "session_id": 42})
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(real_get_db, None)


# ---------------------------------------------------------------------------
# Test 6: GET /chat/sessions/{id} for another user's session is rejected
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_chat_get_session_rejects_foreign(client):
    """GET /chat/sessions/{id} should 403 if session belongs to another user."""
    fake_session = MagicMock()
    fake_session.id = 42
    fake_session.user_id = 999

    fake_user = MagicMock()
    fake_user.id = 1
    fake_user.username = "testuser"
    fake_user.is_active = True

    from app.main import app
    from app.core.deps import get_current_user
    from app.database import get_db as real_get_db

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_session
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[real_get_db] = lambda: mock_session
    try:
        resp = await client.get("/api/chat/sessions/42")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(real_get_db, None)


# ---------------------------------------------------------------------------
# Test 7: POST /chat as anonymous with session_id is rejected
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_chat_anonymous_allowed_without_session(client):
    """Anonymous POST /chat is allowed (returns 503 without LLM config, not 401)."""
    from app.main import app
    from app.core.deps import get_optional_user
    from app.database import get_db as real_get_db

    mock_session = AsyncMock()
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[real_get_db] = lambda: mock_session
    try:
        resp = await client.post("/api/chat", json={"message": "test"})
        # Without LLM API key configured, anonymous chat returns 503
        assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(real_get_db, None)


# ===========================================================================
# Export endpoint tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 8: /api/exports/stats returns counts
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_exports_stats(client):
    """Exports stats endpoint should return entity/text counts."""
    from app.main import app
    from app.database import get_db as real_get_db

    mock_session = AsyncMock()
    # Each count query returns a scalar
    mock_session.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar=MagicMock(return_value=100)),   # text count
            MagicMock(scalar=MagicMock(return_value=50)),    # entity count
            MagicMock(scalar=MagicMock(return_value=30)),    # relation count
        ]
    )

    app.dependency_overrides[real_get_db] = lambda: mock_session
    try:
        resp = await client.get("/api/exports/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "texts" in data
        assert "kg_entities" in data
        assert "kg_relations" in data
    finally:
        app.dependency_overrides.pop(real_get_db, None)


# ===========================================================================
# Knowledge Graph detail endpoint test
# ===========================================================================


# ---------------------------------------------------------------------------
# Test 9: /api/kg/entities/{id} returns full entity detail
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_kg_entity_detail(client):
    """KG entity detail endpoint should return full entity with all fields."""
    fake_entity = MagicMock()
    fake_entity.id = 1
    fake_entity.entity_type = "person"
    fake_entity.name_zh = "鸠摩罗什"
    fake_entity.name_sa = "Kumārajīva"
    fake_entity.name_pi = None
    fake_entity.name_bo = "ཀུ་མཱ་ར་ཛཱི་བ"
    fake_entity.name_en = "Kumārajīva"
    fake_entity.description = "著名佛经翻译家"
    fake_entity.properties = {"birth_year": "344"}
    fake_entity.text_id = None
    fake_entity.external_ids = {"wikidata": "Q334022"}
    fake_entity.created_at = datetime.now(timezone.utc)

    from app.main import app
    from app.database import get_db as real_get_db

    # Mock the DB session; get_entity() calls session.get(KGEntity, id)
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=fake_entity)

    app.dependency_overrides[real_get_db] = lambda: mock_session
    try:
        resp = await client.get("/api/kg/entities/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name_zh"] == "鸠摩罗什"
        assert data["name_sa"] == "Kumārajīva"
        assert data["name_bo"] == "ཀུ་མཱ་ར་ཛཱི་བ"
        assert data["properties"]["birth_year"] == "344"
    finally:
        app.dependency_overrides.pop(real_get_db, None)
