"""Tests for Pydantic schemas (serialization / validation)."""

from app.schemas.text import SearchHit, SearchResponse


class TestSearchHit:
    def test_minimal_hit(self):
        hit = SearchHit(
            id=1,
            cbeta_id="T0001",
            title_zh="长阿含经",
            has_content=True,
        )
        assert hit.id == 1
        assert hit.cbeta_id == "T0001"
        assert hit.translator is None

    def test_full_hit(self):
        hit = SearchHit(
            id=1,
            taisho_id="T01n0001",
            cbeta_id="T0001",
            title_zh="长阿含经",
            translator="佛陀耶舍",
            dynasty="后秦",
            category="阿含部",
            cbeta_url="https://cbetaonline.dila.edu.tw/zh/T0001",
            has_content=True,
            source_code="cbeta",
            score=5.2,
            highlight={"title_zh": ["<em>长阿含经</em>"]},
        )
        assert hit.dynasty == "后秦"
        assert hit.score == 5.2


class TestSearchResponse:
    def test_empty_response(self):
        resp = SearchResponse(total=0, page=1, size=20, results=[])
        assert resp.total == 0
        assert len(resp.results) == 0

    def test_response_with_results(self):
        hit = SearchHit(id=1, cbeta_id="T0001", title_zh="长阿含经", has_content=True)
        resp = SearchResponse(total=1, page=1, size=20, results=[hit])
        assert resp.total == 1
        assert resp.results[0].cbeta_id == "T0001"
