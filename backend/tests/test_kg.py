"""Knowledge Graph API tests — covers search, graph traversal, and filtering.

These tests mock the service layer at the consumer (API router) level
to avoid DB dependencies and test the API contract.
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure elasticsearch stub exists before any app import
if "elasticsearch" not in sys.modules:
    _es_stub = MagicMock()
    _es_stub.AsyncElasticsearch = MagicMock
    sys.modules["elasticsearch"] = _es_stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entity(id, entity_type, name_zh, **kwargs):
    obj = MagicMock()
    obj.id = id
    obj.entity_type = entity_type
    obj.name_zh = name_zh
    obj.name_sa = kwargs.get("name_sa")
    obj.name_pi = kwargs.get("name_pi")
    obj.name_bo = kwargs.get("name_bo")
    obj.name_en = kwargs.get("name_en")
    obj.description = kwargs.get("description")
    obj.properties = kwargs.get("properties")
    obj.text_id = kwargs.get("text_id")
    obj.external_ids = kwargs.get("external_ids")
    obj.relation_count = kwargs.get("relation_count", 0)
    return obj


SEED = [
    _make_entity(1, "person", "法藏", description="华严宗三祖"),
    _make_entity(2, "person", "法藏菩薩", description="大乘菩萨"),
    _make_entity(3, "text", "法藏部", description="一部佛典"),
    _make_entity(4, "person", "玄奘", description="唐代译经师"),
    _make_entity(5, "school", "華嚴宗"),
]

# Patch target: the API module (consumer), NOT the service module (definition)
_KG_API = "app.api.knowledge_graph"


@pytest.fixture
async def kg_client():
    """Async HTTP client with mocked ES/Redis."""
    from httpx import ASGITransport, AsyncClient
    import app.core.elasticsearch  # noqa: F401
    import app.api.search  # noqa: F401
    import app.main  # noqa: F401

    with patch("app.core.elasticsearch.init_es", new_callable=AsyncMock), \
         patch("app.core.elasticsearch.close_es", new_callable=AsyncMock), \
         patch("app.api.search.get_es", return_value=AsyncMock()), \
         patch("app.main.aioredis") as mock_redis:
        mock_redis.from_url.return_value = AsyncMock()
        from app.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Test 1: 搜索返回匹配实体
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_zh_variants(kg_client):
    with patch(f"{_KG_API}.search_entities") as m:
        m.return_value = ([SEED[0]], 1)
        resp = await kg_client.get("/api/kg/entities", params={"q": "法藏"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["results"][0]["name_zh"] == "法藏"


# ---------------------------------------------------------------------------
# Test 2: 搜索相关性排序
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_relevance_order(kg_client):
    with patch(f"{_KG_API}.search_entities") as m:
        m.return_value = ([SEED[0], SEED[1], SEED[2]], 3)
        resp = await kg_client.get("/api/kg/entities", params={"q": "法藏"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 3
        assert results[0]["name_zh"] == "法藏"
        assert results[0]["entity_type"] == "person"
        assert results[2]["entity_type"] == "text"


# ---------------------------------------------------------------------------
# Test 3: 图谱 depth=1 只返回直接邻居
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_graph_depth_boundary(kg_client):
    with patch(f"{_KG_API}.get_entity") as mock_get, \
         patch(f"{_KG_API}.get_entity_graph") as mock_graph:
        mock_get.return_value = SEED[3]
        mock_graph.return_value = {
            "nodes": [
                {"id": 4, "name": "玄奘", "entity_type": "person", "description": None},
                {"id": 8, "name": "成唯識論", "entity_type": "text", "description": None},
            ],
            "links": [
                {"source": 4, "target": 8, "predicate": "translated", "confidence": 1.0,
                 "provenance": "auto:cbeta_metadata", "evidence": None},
            ],
            "truncated": False,
        }
        resp = await kg_client.get("/api/kg/entities/4/graph", params={"depth": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2
        node_ids = {n["id"] for n in data["nodes"]}
        assert 4 in node_ids
        assert 8 in node_ids


# ---------------------------------------------------------------------------
# Test 4: truncated 标记
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_graph_node_limit(kg_client):
    with patch(f"{_KG_API}.get_entity") as mock_get, \
         patch(f"{_KG_API}.get_entity_graph") as mock_graph:
        mock_get.return_value = SEED[3]
        nodes = [{"id": i, "name": f"E{i}", "entity_type": "text", "description": None}
                 for i in range(20)]
        links = [{"source": 0, "target": i, "predicate": "cites", "confidence": 0.7,
                  "provenance": None, "evidence": None} for i in range(1, 20)]
        mock_graph.return_value = {"nodes": nodes, "links": links, "truncated": True}

        resp = await kg_client.get("/api/kg/entities/4/graph",
                                   params={"depth": 3, "max_nodes": 20})
        assert resp.status_code == 200
        assert resp.json()["truncated"] is True


# ---------------------------------------------------------------------------
# Test 5: 谓词过滤
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_graph_predicate_filter(kg_client):
    with patch(f"{_KG_API}.get_entity") as mock_get, \
         patch(f"{_KG_API}.get_entity_graph") as mock_graph:
        mock_get.return_value = SEED[3]
        mock_graph.return_value = {
            "nodes": [
                {"id": 4, "name": "玄奘", "entity_type": "person", "description": None},
                {"id": 5, "name": "華嚴宗", "entity_type": "school", "description": None},
            ],
            "links": [
                {"source": 4, "target": 5, "predicate": "member_of_school",
                 "confidence": 1.0, "provenance": None, "evidence": None},
            ],
            "truncated": False,
        }
        resp = await kg_client.get(
            "/api/kg/entities/4/graph",
            params={"depth": 2, "predicates": "member_of_school,teacher_of"},
        )
        assert resp.status_code == 200
        for link in resp.json()["links"]:
            assert link["predicate"] in ("member_of_school", "teacher_of")


# ---------------------------------------------------------------------------
# Test 6: 实体详情包含 relations
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_entity_detail_includes_relations(kg_client):
    with patch(f"{_KG_API}.get_entity") as mock_get, \
         patch(f"{_KG_API}.get_entity_relations") as mock_rels:
        mock_get.return_value = SEED[0]
        mock_rels.return_value = [
            {
                "predicate": "member_of_school",
                "direction": "outgoing",
                "target_id": 5,
                "target_name": "華嚴宗",
                "target_type": "school",
                "confidence": 1.0,
                "source": "seed:lineage",
            }
        ]
        resp = await kg_client.get("/api/kg/entities/1")
        assert resp.status_code == 200
        data = resp.json()
        assert "relations" in data
        assert len(data["relations"]) == 1
        assert data["relations"][0]["predicate"] == "member_of_school"
        assert data["relations"][0]["target_name"] == "華嚴宗"


# ---------------------------------------------------------------------------
# Test 8: 时间轴端点返回实体列表及 total
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_timeline_returns_entities(kg_client):
    timeline_entities = [
        {"id": 4, "name_zh": "玄奘", "entity_type": "person",
         "year_start": 602, "year_end": 664},
        {"id": 6, "name_zh": "法显", "entity_type": "person",
         "year_start": 337, "year_end": 422},
    ]
    with patch(f"{_KG_API}.get_timeline_entities") as m:
        m.return_value = (timeline_entities, 2)
        resp = await kg_client.get("/api/kg/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["entities"]) == 2
        assert data["entities"][0]["name_zh"] == "玄奘"
        assert data["entities"][0]["year_start"] == 602
        assert data["entities"][0]["year_end"] == 664


# ---------------------------------------------------------------------------
# Test 9: 时间轴端点支持 entity_type 过滤
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_timeline_entity_type_filter(kg_client):
    dynasty_entity = [
        {"id": 10, "name_zh": "唐朝", "entity_type": "dynasty",
         "year_start": 618, "year_end": 907},
    ]
    with patch(f"{_KG_API}.get_timeline_entities") as m:
        m.return_value = (dynasty_entity, 1)
        resp = await kg_client.get("/api/kg/timeline", params={"entity_type": "dynasty"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["entities"][0]["entity_type"] == "dynasty"
        # Verify service was called with the filter
        m.assert_called_once()
        call_kwargs = m.call_args
        assert call_kwargs[0][1] == "dynasty" or call_kwargs[1].get("entity_type") == "dynasty"


# ---------------------------------------------------------------------------
# Test 10: 时间轴端点正确处理 BCE（负数）年份
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_timeline_bce_years(kg_client):
    bce_entity = [
        {"id": 20, "name_zh": "龙树", "entity_type": "person",
         "year_start": -150, "year_end": -70},
    ]
    with patch(f"{_KG_API}.get_timeline_entities") as m:
        m.return_value = (bce_entity, 1)
        resp = await kg_client.get("/api/kg/timeline")
        assert resp.status_code == 200
        entities = resp.json()["entities"]
        assert entities[0]["year_start"] == -150
        assert entities[0]["year_end"] == -70


# ---------------------------------------------------------------------------
# Test 11: 时间轴端点处理 year_end 为空的实体
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_timeline_missing_year_end(kg_client):
    partial_entity = [
        {"id": 30, "name_zh": "某法师", "entity_type": "person",
         "year_start": 800, "year_end": None},
    ]
    with patch(f"{_KG_API}.get_timeline_entities") as m:
        m.return_value = (partial_entity, 1)
        resp = await kg_client.get("/api/kg/timeline")
        assert resp.status_code == 200
        entities = resp.json()["entities"]
        assert entities[0]["year_start"] == 800
        assert entities[0]["year_end"] is None


# ---------------------------------------------------------------------------
# Test 7: 搜索结果透出 relation_count（图度数），供前端排序徽章使用
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_search_results_expose_relation_count(kg_client):
    with patch(f"{_KG_API}.search_entities") as m:
        m.return_value = (
            [
                _make_entity(1, "person", "玄奘", relation_count=42),
                _make_entity(2, "person", "玄奘三藏", relation_count=0),
            ],
            2,
        )
        resp = await kg_client.get("/api/kg/entities", params={"q": "玄奘"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["relation_count"] == 42
        assert results[1]["relation_count"] == 0
