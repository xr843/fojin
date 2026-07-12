"""GET /alignment/chunks/{text_id}/{juan_num}/{chunk_index} response contract.

The endpoint was refactored onto services/alignment_read_model; its HTTP
response shape is a frozen contract with the frontend (client.ts
getChunkAlignment) and existing deep-links. These tests pin the exact JSON:
key set, MITRA presentation (ids=0, title MITRA 平行（梵/藏）,
source="mitra-parallel"), fojin defaults (lang→lzh, source="fojin"), and the
limit validation bounds.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.alignment_read_model import ParallelRecord, SegmentRef

# The frozen wire shape of one parallel (ParallelPair).
PARALLEL_KEYS = {
    "text_id", "juan_num", "chunk_index", "chunk_text", "lang", "title",
    "confidence", "original_preview", "original_lang", "source",
}
RESPONSE_KEYS = {"source_text_id", "source_juan_num", "source_chunk_index", "parallels"}


def _fojin_record(**over):
    base = dict(
        granularity="chunk",
        source="embed_llm",
        confidence=0.95,
        confidence_kind="llm",
        self_ref=SegmentRef(text_id=1, juan_num=2, chunk_index=3, lang="lzh"),
        other_ref=SegmentRef(text_id=200, juan_num=1, chunk_index=4, lang="pi"),
        preview="english translation of the pali chunk",
        title="Majjhima Nikāya",
        original_preview="Evaṃ me sutaṃ",
        original_lang="pi",
    )
    base.update(over)
    return ParallelRecord(**base)


def _mitra_record(foreign_lang="sa", **over):
    base = dict(
        granularity="chunk",
        source="mitra",
        confidence=1.0,
        confidence_kind="import_flag",
        self_ref=SegmentRef(text_id=1, juan_num=2, chunk_index=3, lang="lzh"),
        other_ref=SegmentRef(text_id=None, lang=foreign_lang),
        preview="evaṃ mayā śrutam",
    )
    base.update(over)
    return ParallelRecord(**base)


@pytest.mark.asyncio
async def test_response_shape_unchanged(client):
    records = [_fojin_record(), _mitra_record("sa"), _mitra_record("bo")]
    with patch(
        "app.api.alignment.get_chunk_parallels", new=AsyncMock(return_value=records)
    ) as svc:
        resp = await client.get("/api/alignment/chunks/1/2/3")

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == RESPONSE_KEYS
    assert data["source_text_id"] == 1
    assert data["source_juan_num"] == 2
    assert data["source_chunk_index"] == 3
    assert len(data["parallels"]) == 3
    for p in data["parallels"]:
        assert set(p.keys()) == PARALLEL_KEYS

    fojin = data["parallels"][0]
    assert fojin == {
        "text_id": 200,
        "juan_num": 1,
        "chunk_index": 4,
        "chunk_text": "english translation of the pali chunk",
        "lang": "pi",
        "title": "Majjhima Nikāya",
        "confidence": 0.95,
        "original_preview": "Evaṃ me sutaṃ",
        "original_lang": "pi",
        "source": "fojin",
    }

    sa = data["parallels"][1]
    assert sa == {
        "text_id": 0,
        "juan_num": 0,
        "chunk_index": 0,
        "chunk_text": "evaṃ mayā śrutam",
        "lang": "sa",
        "title": "MITRA 平行（梵）",
        "confidence": 1.0,
        "original_preview": None,
        "original_lang": None,
        "source": "mitra-parallel",
    }
    assert data["parallels"][2]["title"] == "MITRA 平行（藏）"
    assert data["parallels"][2]["lang"] == "bo"

    # The service does the merge; the endpoint only adapts.
    svc.assert_awaited_once()
    assert svc.await_args.kwargs["limit"] == 5  # default query param


@pytest.mark.asyncio
async def test_limit_param_forwarded_to_service(client):
    with patch(
        "app.api.alignment.get_chunk_parallels", new=AsyncMock(return_value=[])
    ) as svc:
        resp = await client.get("/api/alignment/chunks/1/1/0", params={"limit": 7})
    assert resp.status_code == 200
    assert resp.json()["parallels"] == []
    assert svc.await_args.kwargs["limit"] == 7


@pytest.mark.asyncio
async def test_limit_validation_bounds_preserved(client):
    with patch("app.api.alignment.get_chunk_parallels", new=AsyncMock(return_value=[])):
        assert (await client.get("/api/alignment/chunks/1/1/0", params={"limit": 0})).status_code == 422
        assert (await client.get("/api/alignment/chunks/1/1/0", params={"limit": 21})).status_code == 422
        assert (await client.get("/api/alignment/chunks/1/1/0", params={"limit": 20})).status_code == 200


@pytest.mark.asyncio
async def test_fojin_lang_falls_back_to_lzh(client):
    records = [_fojin_record(
        other_ref=SegmentRef(text_id=300, juan_num=2, chunk_index=7, lang=None),
        original_preview=None, original_lang=None,
    )]
    with patch("app.api.alignment.get_chunk_parallels", new=AsyncMock(return_value=records)):
        resp = await client.get("/api/alignment/chunks/1/2/3")
    p = resp.json()["parallels"][0]
    assert p["lang"] == "lzh"
    assert p["source"] == "fojin"
