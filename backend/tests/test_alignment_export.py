"""Tests for the shared alignment-dataset export logic + the HTTP endpoint.

The pure builders (row → record, license aggregation, card) carry the real
logic, so they are unit-tested directly on lightweight fixture rows — no DB.
The DB orchestrators are exercised with a fake session factory (mirroring the
mock-DB pattern of test_alignment_read_model.py). The endpoint is wired by
patching the two service functions it composes.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import alignment_export
from app.services.alignment_export import (
    DATASET_LICENSE,
    DATASET_NAME,
    DEFAULT_VERSION,
    aggregate_source_licenses,
    build_card,
    chunk_row_to_record,
    collect_card_facts,
    iter_records,
    sentence_row_to_record,
)

# --- fixture rows ------------------------------------------------------------


def _chunk_row(**kw):
    """A labeled chunk row as the SELECT returns it (attribute access)."""
    base = dict(
        id=101,
        lang_src="pi",
        lang_tgt="lzh",
        src_text_id=200,
        src_canonical_id="SC-mn10",
        src_title="Satipaṭṭhānasutta",
        src_juan=1,
        src_chunk=4,
        src_license_spdx="CC0-1.0",
        src_license_url="https://suttacentral.net/licensing",
        src_source_name_zh="巴利圣典协会",
        src_source_name_en="SuttaCentral",
        src_attr_required=True,
        tgt_text_id=300,
        tgt_canonical_id="T0026",
        tgt_title="中阿含經",
        tgt_juan=2,
        tgt_chunk=7,
        tgt_license_spdx="CC-BY-NC-SA-4.0",
        tgt_license_url="https://www.cbeta.org/copyright.php",
        tgt_source_name_zh="中華電子佛典協會",
        tgt_source_name_en="CBETA",
        tgt_attr_required=True,
        segment_src="Evaṃ me sutaṃ ...",
        segment_tgt="我聞如是 ...",
        confidence=0.92,
        method="embed_llm",
        is_verified=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _sentence_row(**kw):
    base = dict(
        id=1,
        align_type="1-1",
        similarity=0.87,
        method="sentence-bertalign",
        src_text_id=200,
        src_title="Satipaṭṭhānasutta",
        src_juan=1,
        src_char_start=10,
        src_char_end=55,
        src_lang="pi",
        src_text="Evaṃ me sutaṃ",
        src_license_spdx="CC0-1.0",
        src_license_url="https://suttacentral.net/licensing",
        src_source_name_zh="巴利圣典协会",
        src_source_name_en="SuttaCentral",
        src_attr_required=True,
        tgt_text_id=300,
        tgt_title="中阿含經",
        tgt_juan=2,
        tgt_char_start=0,
        tgt_char_end=40,
        tgt_lang="lzh",
        tgt_text="我聞如是",
        tgt_license_spdx="CC-BY-NC-SA-4.0",
        tgt_license_url="https://www.cbeta.org/copyright.php",
        tgt_source_name_zh="中華電子佛典協會",
        tgt_source_name_en="CBETA",
        tgt_attr_required=True,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- chunk record shape (backward compatible + additive license) -------------


def test_chunk_record_preserves_legacy_fields():
    rec = chunk_row_to_record(_chunk_row())
    # Every field the pre-license exporter emitted must still be present & unchanged.
    assert rec["id"] == 101
    assert rec["lang_src"] == "pi" and rec["lang_tgt"] == "lzh"
    assert rec["segment_src"] == "Evaṃ me sutaṃ ..."
    assert rec["segment_tgt"] == "我聞如是 ..."
    assert rec["confidence"] == 0.92
    assert rec["method"] == "embed_llm"
    assert rec["verified"] is False
    for side, tid, cid, chunk in (("src", 200, "SC-mn10", 4), ("tgt", 300, "T0026", 7)):
        assert rec[side]["text_id"] == tid
        assert rec[side]["canonical_id"] == cid
        assert rec[side]["chunk_index"] == chunk
        assert "title" in rec[side] and "juan" in rec[side]


def test_chunk_record_adds_per_side_license_and_attribution():
    rec = chunk_row_to_record(_chunk_row())
    assert rec["src"]["license"] == {"spdx": "CC0-1.0", "url": "https://suttacentral.net/licensing"}
    assert rec["src"]["attribution"] == "SuttaCentral (CC0-1.0)"
    assert rec["tgt"]["license"] == {
        "spdx": "CC-BY-NC-SA-4.0",
        "url": "https://www.cbeta.org/copyright.php",
    }
    assert rec["tgt"]["attribution"] == "CBETA (CC-BY-NC-SA-4.0)"


def test_chunk_record_missing_source_license_is_null_not_error():
    row = _chunk_row(
        src_license_spdx=None,
        src_license_url=None,
        src_source_name_zh=None,
        src_source_name_en=None,
        src_attr_required=None,
    )
    rec = chunk_row_to_record(row)
    assert rec["src"]["license"] is None
    assert rec["src"]["attribution"] is None
    # tgt side still populated — one missing source must not blank the other.
    assert rec["tgt"]["license"]["spdx"] == "CC-BY-NC-SA-4.0"


def test_chunk_record_is_json_serializable():
    json.dumps(chunk_row_to_record(_chunk_row()), ensure_ascii=False)


# --- sentence record shape ---------------------------------------------------


def test_sentence_record_shape():
    rec = sentence_row_to_record(_sentence_row())
    assert rec["id"] == 1
    assert rec["align_type"] == "1-1"
    assert rec["similarity"] == 0.87
    assert rec["method"] == "sentence-bertalign"
    # src carries char offsets + the sentence text under `text`, plus license.
    assert rec["src"]["char_start"] == 10 and rec["src"]["char_end"] == 55
    assert rec["src"]["lang"] == "pi"
    assert rec["src"]["text"] == "Evaṃ me sutaṃ"
    assert rec["src"]["license"] == {"spdx": "CC0-1.0", "url": "https://suttacentral.net/licensing"}
    assert rec["tgt"]["text"] == "我聞如是"
    assert rec["tgt"]["attribution"] == "CBETA (CC-BY-NC-SA-4.0)"
    # sentence records have no chunk_index / confidence / verified keys.
    assert "chunk_index" not in rec["src"]
    assert "confidence" not in rec


# --- license aggregation from mixed sources ----------------------------------


def test_aggregate_source_licenses_dedups_and_sorts():
    # rows: (spdx, url, name_zh, name_en, attribution_required)
    rows = [
        ("CC-BY-NC-SA-4.0", "https://cbeta", "中華電子佛典協會", "CBETA", True),
        ("CC0-1.0", "https://sc", "巴利圣典协会", "SuttaCentral", False),
        ("CC-BY-NC-SA-4.0", "https://cbeta", "中華電子佛典協會", "CBETA", True),  # dup
        ("CC-BY-NC-ND-4.0", "https://84000", None, "84000", True),
        (None, None, None, None, None),  # no source info → dropped
    ]
    out = aggregate_source_licenses(rows)
    names = [x["source"] for x in out]
    assert names == ["84000", "CBETA", "SuttaCentral"]  # sorted, deduped
    cbeta = next(x for x in out if x["source"] == "CBETA")
    assert cbeta["spdx"] == "CC-BY-NC-SA-4.0"
    assert cbeta["attribution_required"] is True
    sc = next(x for x in out if x["source"] == "SuttaCentral")
    assert sc["attribution_required"] is False


def test_aggregate_source_licenses_empty():
    assert aggregate_source_licenses([]) == []


# --- dataset card ------------------------------------------------------------


def test_build_card_full():
    licenses = [{"source": "CBETA", "spdx": "CC-BY-NC-SA-4.0", "url": "x", "attribution_required": True}]
    card = build_card(
        granularity="chunk",
        version="1.0.0",
        generated_at="2026-07-11",
        record_count=12345,
        source_licenses=licenses,
    )
    assert card["dataset"] == DATASET_NAME
    assert card["version"] == "1.0.0"
    assert card["generated_at"] == "2026-07-11"
    assert card["record_count"] == 12345
    assert card["granularity"] == "chunk"
    assert card["license"] == DATASET_LICENSE == "CC-BY-SA-4.0"
    assert card["source_licenses"] == licenses
    assert "1.0.0" in card["citation"]
    assert card["provenance_note"]  # non-empty


def test_build_card_omits_generated_at_when_none_and_defaults_version():
    card = build_card(
        granularity="sentence",
        version=None,
        generated_at=None,
        record_count=0,
        source_licenses=[],
    )
    assert "generated_at" not in card
    assert card["version"] == DEFAULT_VERSION
    # empty sentence table → a valid card with count 0.
    assert card["record_count"] == 0
    assert card["granularity"] == "sentence"
    assert card["source_licenses"] == []


# --- fake session factory for the DB orchestrators ---------------------------


class _FakeFactory:
    """Callable returning an async-context-manager session whose execute()
    returns queued fetchall() results in order. Records every execute call."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = []
        self.session = MagicMock()
        self.session.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, stmt, params):
        self.calls.append((stmt, params))
        result = MagicMock()
        result.fetchall.return_value = self._results.pop(0)
        return result

    def __call__(self):
        factory = self

        class _Ctx:
            async def __aenter__(self):
                return factory.session

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


@pytest.mark.asyncio
async def test_iter_records_paginates_and_applies_method_filter():
    # First batch returns two rows, second batch empty → loop stops.
    factory = _FakeFactory([_chunk_row(id=101), _chunk_row(id=102)], [])
    recs = [
        r
        async for r in iter_records(
            granularity="chunk",
            min_confidence=0.8,
            methods=["manual", "expert"],
            batch_size=2,
            session_factory=factory,
        )
    ]
    assert [r["id"] for r in recs] == [101, 102]
    # keyset advanced past the last id; the method list reached the query params.
    first_params = factory.calls[0][1]
    assert first_params["methods"] == ["manual", "expert"]
    assert first_params["min_confidence"] == 0.8
    assert first_params["last_id"] == 0
    assert factory.calls[1][1]["last_id"] == 102  # advanced by keyset


@pytest.mark.asyncio
async def test_iter_records_no_method_filter_omits_param():
    factory = _FakeFactory([_chunk_row(id=1)], [])
    _ = [r async for r in iter_records(granularity="chunk", batch_size=5, session_factory=factory)]
    assert "methods" not in factory.calls[0][1]


@pytest.mark.asyncio
async def test_collect_card_facts_counts_and_aggregates_licenses():
    # execute order: COUNT, then side-A distinct licenses, then side-B.
    count_result = [(2,)]
    side_a = [("CC0-1.0", "https://sc", "巴利圣典协会", "SuttaCentral", False)]
    side_b = [("CC-BY-NC-SA-4.0", "https://cbeta", "中華電子佛典協會", "CBETA", True)]
    factory = _FakeFactory(count_result, side_a, side_b)
    count, licenses = await collect_card_facts(granularity="chunk", session_factory=factory)
    assert count == 2
    assert [x["source"] for x in licenses] == ["CBETA", "SuttaCentral"]


@pytest.mark.asyncio
async def test_collect_card_facts_empty_sentence_table():
    factory = _FakeFactory([(0,)], [], [])
    count, licenses = await collect_card_facts(granularity="sentence", session_factory=factory)
    assert count == 0
    assert licenses == []


def test_unknown_granularity_rejected():
    with pytest.raises(ValueError):
        alignment_export._config("paragraph")


# --- HTTP endpoint -----------------------------------------------------------


async def _fake_iter_records(**kwargs):
    for i in (101, 102):
        yield {"id": i, "lang_src": "pi", "lang_tgt": "lzh"}


@pytest.mark.asyncio
async def test_endpoint_streams_card_then_records(open_data_exports_enabled, client):
    facts = AsyncMock(
        return_value=(2, [{"source": "CBETA", "spdx": "CC-BY-NC-SA-4.0", "url": "x", "attribution_required": True}])
    )
    with (
        patch("app.services.alignment_export.collect_card_facts", facts),
        patch("app.services.alignment_export.iter_records", _fake_iter_records),
    ):
        resp = await client.get("/api/exports/alignments.jsonl?granularity=chunk&methods=manual,expert")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    assert "fojin_alignments_chunk.jsonl" in resp.headers["content-disposition"]

    lines = [json.loads(ln) for ln in resp.text.strip().split("\n")]
    card = lines[0]
    assert card["dataset"] == DATASET_NAME  # first line is the card
    assert card["license"] == "CC-BY-SA-4.0"
    assert card["record_count"] == 2
    assert card["source_licenses"][0]["source"] == "CBETA"
    assert [r["id"] for r in lines[1:]] == [101, 102]  # then the records


async def _empty_iter_records(**kwargs):
    return
    yield  # pragma: no cover  (makes this an async generator)


@pytest.mark.asyncio
async def test_endpoint_empty_sentence_table_yields_card_count_zero(open_data_exports_enabled, client):
    with (
        patch("app.services.alignment_export.collect_card_facts", AsyncMock(return_value=(0, []))),
        patch("app.services.alignment_export.iter_records", _empty_iter_records),
    ):
        resp = await client.get("/api/exports/alignments.jsonl?granularity=sentence")
    assert resp.status_code == 200
    lines = resp.text.strip().split("\n")
    assert len(lines) == 1  # only the card, no records
    card = json.loads(lines[0])
    assert card["granularity"] == "sentence"
    assert card["record_count"] == 0
    assert card["source_licenses"] == []


@pytest.mark.asyncio
async def test_endpoint_rejects_bad_granularity(open_data_exports_enabled, client):
    resp = await client.get("/api/exports/alignments.jsonl?granularity=paragraph")
    assert resp.status_code == 422
