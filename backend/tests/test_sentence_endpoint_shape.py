"""GET /alignment/sentences/{text_id}/{juan_num} response contract.

Phase 4 Package C read path, shipped DARK behind settings.enable_sentence_parallels.
The endpoint is a thin adapter over services.get_sentence_parallels; its HTTP
response shape is a frozen contract with the frontend (client.ts, future 逐句对读
reader view), parallel to the chunk endpoints. These tests pin:

  * the dark-ship gate: flag OFF returns total=0/pairs=[] WITHOUT ever calling
    the service (no DB touch);
  * flag ON + empty table → the same empty payload (never an error), but the
    service IS invoked;
  * flag ON + rows → the exact JSON key set and mapped values (side_a = the
    requested text, side_b = the counterpart);
  * limit forwarding + validation bounds.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.api import alignment as alignment_api
from app.services.alignment_read_model import SegmentRef, SentencePairRecord

# The frozen wire shape.
RESPONSE_KEYS = {"text_id", "juan_num", "total", "pairs"}
PAIR_KEYS = {"side_a", "side_b", "similarity", "align_type", "method", "is_verified"}
SIDE_A_KEYS = {"char_start", "char_end", "lang", "text"}
SIDE_B_KEYS = {"text_id", "juan_num", "char_start", "char_end", "lang", "title", "text"}


def _record(**over):
    base = dict(
        self_ref=SegmentRef(text_id=1, juan_num=5, lang="lzh", char_start=0, char_end=40),
        other_ref=SegmentRef(text_id=200, juan_num=1, lang="pi", char_start=0, char_end=60),
        self_text="如是我聞",
        other_text="Evaṃ me sutaṃ",
        similarity=0.95,
        align_type="1-1",
        method="sentence-bertalign",
        is_verified=True,
        title="Majjhima Nikāya",
    )
    base.update(over)
    return SentencePairRecord(**base)


@pytest.mark.asyncio
async def test_flag_off_returns_dark_empty_without_querying(client, monkeypatch):
    """Default (flag off): clean empty payload, service never touched."""
    monkeypatch.setattr(alignment_api.settings, "enable_sentence_parallels", False)
    with patch(
        "app.api.alignment.get_sentence_parallels", new=AsyncMock(return_value=[_record()])
    ) as svc:
        resp = await client.get("/api/alignment/sentences/1/5")

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == RESPONSE_KEYS
    assert data == {"text_id": 1, "juan_num": 5, "total": 0, "pairs": []}
    svc.assert_not_awaited()  # dark ship: no DB work at all


@pytest.mark.asyncio
async def test_flag_on_empty_table_returns_empty_but_queries(client, monkeypatch):
    monkeypatch.setattr(alignment_api.settings, "enable_sentence_parallels", True)
    with patch(
        "app.api.alignment.get_sentence_parallels", new=AsyncMock(return_value=[])
    ) as svc:
        resp = await client.get("/api/alignment/sentences/1/5")

    assert resp.status_code == 200
    assert resp.json() == {"text_id": 1, "juan_num": 5, "total": 0, "pairs": []}
    svc.assert_awaited_once()  # flag on: it does query, table just has no rows


@pytest.mark.asyncio
async def test_flag_on_rows_map_to_frozen_shape(client, monkeypatch):
    monkeypatch.setattr(alignment_api.settings, "enable_sentence_parallels", True)
    records = [
        _record(),
        _record(
            other_ref=SegmentRef(text_id=300, juan_num=2, lang="lzh", char_start=None, char_end=None),
            other_text="爾時世尊",
            similarity=0.80,
            align_type="1-2",
            method="manual",
            is_verified=False,
            title="別譯雜阿含經",
        ),
    ]
    with patch(
        "app.api.alignment.get_sentence_parallels", new=AsyncMock(return_value=records)
    ) as svc:
        resp = await client.get("/api/alignment/sentences/1/5")

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == RESPONSE_KEYS
    assert data["text_id"] == 1 and data["juan_num"] == 5 and data["total"] == 2
    for p in data["pairs"]:
        assert set(p.keys()) == PAIR_KEYS
        assert set(p["side_a"].keys()) == SIDE_A_KEYS
        assert set(p["side_b"].keys()) == SIDE_B_KEYS

    assert data["pairs"][0] == {
        "side_a": {"char_start": 0, "char_end": 40, "lang": "lzh", "text": "如是我聞"},
        "side_b": {
            "text_id": 200, "juan_num": 1, "char_start": 0, "char_end": 60,
            "lang": "pi", "title": "Majjhima Nikāya", "text": "Evaṃ me sutaṃ",
        },
        "similarity": 0.95,
        "align_type": "1-1",
        "method": "sentence-bertalign",
        "is_verified": True,
    }
    # Counterpart offsets not yet backfilled coerce to 0 (never null) on the wire.
    second = data["pairs"][1]
    assert second["side_b"]["char_start"] == 0 and second["side_b"]["char_end"] == 0
    assert second["is_verified"] is False

    svc.assert_awaited_once()
    assert svc.await_args.kwargs["limit"] == 200  # default query param forwarded


@pytest.mark.asyncio
async def test_limit_forwarded_and_validation_bounds(client, monkeypatch):
    monkeypatch.setattr(alignment_api.settings, "enable_sentence_parallels", True)
    with patch(
        "app.api.alignment.get_sentence_parallels", new=AsyncMock(return_value=[])
    ) as svc:
        resp = await client.get("/api/alignment/sentences/1/5", params={"limit": 50})
        assert resp.status_code == 200
        assert svc.await_args.kwargs["limit"] == 50

        # Bounds are enforced by FastAPI before the handler body runs.
        assert (await client.get("/api/alignment/sentences/1/5", params={"limit": 0})).status_code == 422
        assert (await client.get("/api/alignment/sentences/1/5", params={"limit": 501})).status_code == 422
        assert (await client.get("/api/alignment/sentences/1/5", params={"limit": 500})).status_code == 200
