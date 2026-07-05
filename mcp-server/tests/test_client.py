"""Tests for FojinClient's reshaping + HTTP behaviour.

The pure ``shape_*`` functions are tested with plain dicts (no I/O). The client
methods are tested against a mocked httpx transport so we assert the exact
request path/params AND that every returned passage carries a URN — without
touching the network.
"""

import httpx
import pytest

from fojin_mcp.client import (
    FojinAPIError,
    FojinClient,
    shape_parallels,
    shape_passage,
    shape_search_results,
)


# ── pure reshaping ───────────────────────────────────────────────────────


def test_shape_search_results_adds_urn_per_hit():
    data = {
        "total": 2,
        "results": [
            {"text_id": 5, "juan_num": 1, "title_zh": "心經", "cbeta_id": "T0251",
             "snippet": "色即是空", "similarity_score": 0.91},
            {"text_id": 9, "juan_num": 2, "title_zh": "中部", "cbeta_id": "SC-mn10",
             "snippet": "satipaṭṭhāna", "similarity_score": 0.83},
        ],
    }
    out = shape_search_results(data)
    assert out["total"] == 2
    assert out["results"][0]["urn"] == "fojin:cbeta/T0251.1"
    assert out["results"][0]["score"] == 0.91
    assert out["results"][1]["urn"] == "fojin:sc/mn10.2"


def test_shape_search_results_urn_none_when_no_cbeta_id():
    out = shape_search_results({"results": [{"text_id": 1, "juan_num": 1, "title_zh": "x"}]})
    assert out["results"][0]["urn"] is None


def test_shape_search_results_tolerates_garbage():
    assert shape_search_results(None) == {"total": 0, "results": []}
    assert shape_search_results({"results": ["notadict", 5]})["results"] == []


def test_shape_passage_adds_urn():
    data = {"text_id": 5, "cbeta_id": "T0251", "title_zh": "心經", "juan_num": 1,
            "total_juans": 1, "content": "觀自在菩薩…", "char_count": 260, "lang": "lzh"}
    out = shape_passage(data)
    assert out["urn"] == "fojin:cbeta/T0251.1"
    assert out["content"].startswith("觀自在")


def test_shape_parallels_flattens_real_envelope():
    """Real shape: entries[] -> parallels[] (ParallelPair, keyed by text_id)."""
    data = {
        "text_id": 5, "juan_num": 1, "total_chunks": 10, "chunks_with_parallels": 1,
        "entries": [
            {"chunk_index": 2, "chunk_text": "汉文源文", "parallels": [
                {"text_id": 99, "juan_num": 1, "chunk_index": 0, "lang": "pi",
                 "title": "Majjhima 10", "chunk_text": "pali para", "confidence": 0.88,
                 "source": "fojin"},
                {"text_id": 0, "juan_num": 0, "chunk_index": 0, "lang": "sa",
                 "title": "", "chunk_text": "", "confidence": 1.0,
                 "source": "mitra-parallel", "original_preview": "skt sentence",
                 "original_lang": "sa"},
            ]},
        ],
    }
    out = shape_parallels(data)
    assert out["source"]["text_id"] == 5
    assert out["source"]["chunks_with_parallels"] == 1
    assert len(out["parallels"]) == 2
    p0 = out["parallels"][0]
    assert p0["urn"] is None                      # filled later by enrichment
    assert p0["lang"] == "pi"
    assert p0["aligns_source_chunk"] == 2
    assert p0["reader_ref"] == {"text_id": 99, "juan_num": 1, "chunk_index": 0}
    # MITRA inline foreign sentence: no fojin work → text_id 0, keeps preview.
    assert out["parallels"][1]["source"] == "mitra-parallel"
    assert out["parallels"][1]["original_preview"] == "skt sentence"


def test_shape_parallels_tolerates_empty():
    assert shape_parallels({})["parallels"] == []
    assert shape_parallels({"entries": []})["parallels"] == []


# ── client HTTP behaviour (mocked transport) ─────────────────────────────


def _client_with(handler) -> FojinClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="http://test")
    return FojinClient("http://test/api", client=http)


@pytest.mark.asyncio
async def test_search_corpus_hits_semantic_endpoint_with_clamped_size():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 1, "results": [
            {"text_id": 5, "juan_num": 1, "title_zh": "心經", "cbeta_id": "T0251",
             "snippet": "色即是空", "similarity_score": 0.9}]})

    async with _client_with(handler) as c:
        out = await c.search_corpus("空", limit=999, lang="lzh")

    assert seen["path"] == "/api/search/semantic"
    assert seen["params"]["q"] == "空"
    assert seen["params"]["size"] == "50"          # clamped 999 → 50
    assert seen["params"]["lang"] == "lzh"
    assert out["results"][0]["urn"] == "fojin:cbeta/T0251.1"


@pytest.mark.asyncio
async def test_read_passage_path_and_urn():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/texts/5/juans/1"
        return httpx.Response(200, json={
            "text_id": 5, "cbeta_id": "T0251", "title_zh": "心經", "juan_num": 1,
            "total_juans": 1, "content": "觀自在菩薩", "char_count": 5, "lang": "lzh"})

    async with _client_with(handler) as c:
        out = await c.read_passage(5, 1)
    assert out["urn"] == "fojin:cbeta/T0251.1"


@pytest.mark.asyncio
async def test_resolve_urn_percent_encodes_anchor():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # httpx exposes the DECODED param; assert the anchor survived (wasn't
        # stripped as a fragment) by checking the raw query carries %2523/%23.
        seen["raw_query"] = request.url.query.decode()
        return httpx.Response(200, json={"urn": "fojin:cbeta/T0001.1", "exists": True})

    async with _client_with(handler) as c:
        await c.resolve_urn("fojin:cbeta/T0001.1#p0001a01")
    # The '#' was replaced with %23 before sending, so no fragment was dropped.
    assert "p0001a01" in seen["raw_query"]


@pytest.mark.asyncio
async def test_get_parallels_enriches_urns_via_text_lookup():
    """A fojin-native parallel (text_id 99) gets a URN from a text_id→cbeta_id
    lookup; a MITRA inline parallel (text_id 0) stays urn=None."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/alignment/texts/5/juans/1":
            return httpx.Response(200, json={
                "text_id": 5, "juan_num": 1, "total_chunks": 3, "chunks_with_parallels": 1,
                "entries": [{"chunk_index": 0, "chunk_text": "源", "parallels": [
                    {"text_id": 99, "juan_num": 2, "chunk_index": 0, "lang": "pi",
                     "title": "M10", "chunk_text": "p", "confidence": 0.9, "source": "fojin"},
                    {"text_id": 0, "juan_num": 0, "chunk_index": 0, "lang": "sa",
                     "title": "", "chunk_text": "", "confidence": 1.0,
                     "source": "mitra-parallel", "original_preview": "s", "original_lang": "sa"},
                ]}],
            })
        if path == "/api/texts/99":
            return httpx.Response(200, json={"text_id": 99, "cbeta_id": "SC-mn10",
                                             "title_zh": "中部", "juan_num": 2})
        return httpx.Response(404, json={"detail": "unexpected " + path})

    async with _client_with(handler) as c:
        out = await c.get_parallels(5, 1)

    fojin_par = out["parallels"][0]
    assert fojin_par["reader_ref"]["text_id"] == 99
    assert fojin_par["urn"] == "fojin:sc/mn10.2"     # enriched from /texts/99
    assert out["parallels"][1]["urn"] is None         # MITRA inline, unresolvable


@pytest.mark.asyncio
async def test_get_parallels_survives_enrichment_lookup_failure():
    """A failed text lookup during enrichment must leave urn=None, not raise."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/alignment"):
            return httpx.Response(200, json={"text_id": 5, "juan_num": 1,
                "total_chunks": 1, "chunks_with_parallels": 1,
                "entries": [{"chunk_index": 0, "chunk_text": "源", "parallels": [
                    {"text_id": 99, "juan_num": 1, "chunk_index": 0, "lang": "pi",
                     "title": "M", "chunk_text": "p", "confidence": 0.9, "source": "fojin"}]}]})
        return httpx.Response(500, json={"detail": "boom"})   # /texts/99 fails

    async with _client_with(handler) as c:
        out = await c.get_parallels(5, 1)
    assert out["parallels"][0]["urn"] is None


@pytest.mark.asyncio
async def test_http_error_becomes_fojin_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    async with _client_with(handler) as c:
        with pytest.raises(FojinAPIError):
            await c.read_passage(1, 1)
