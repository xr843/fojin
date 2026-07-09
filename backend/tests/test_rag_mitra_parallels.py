"""Tests for feeding MITRA parallels into the chat RAG context.

`mitra_alignments` (~908K Skt/Tib↔汉 sentence pairs, chunk-anchored on the 汉
side) is surfaced to the answer side as an LLM-context-only `mitra_parallels`
field. A chunk anchors many MITRA sentences, so `_attach_mitra_parallels` fetches
a confidence pool then re-ranks it by relevance to the question
(`_rank_mitra_by_relevance`) — so 「色即是空」's Sanskrit wins over an arbitrary
「受想行识」 sentence in the same chunk. `_format_context_block` renders the top
results in [跨藏对读], deduped by language.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rag_retrieval import (
    MITRA_PARALLEL_SHOW,
    _attach_mitra_parallels,
    _cjk_overlap,
    _format_context_block,
    _group_mitra_rows,
    _rank_mitra_by_relevance,
)


def _make_db_with_rows(rows):
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


# ── _group_mitra_rows (pure) ──────────────────────────────────────────

def test_group_mitra_rows_groups_and_skips_empty():
    # row shape: (primary_idx, foreign_lang, foreign_text, zh_text, confidence)
    rows = [
        (0, "sa", "sanskrit A", "汉A", 0.99),
        (0, "bo", "tibetan A", "汉B", 0.90),
        (0, "sa", "", "汉C", 0.80),        # empty foreign_text → skipped
        (2, "bo", "tibetan B", "汉D", 0.70),
    ]
    grouped = _group_mitra_rows(rows)
    assert set(grouped.keys()) == {0, 2}
    assert [p["chunk_text"] for p in grouped[0]] == ["sanskrit A", "tibetan A"]
    assert grouped[0][0] == {"lang": "sa", "chunk_text": "sanskrit A", "zh_text": "汉A", "confidence": 0.99}
    assert grouped[2][0]["lang"] == "bo"


# ── relevance ranking (pure) ──────────────────────────────────────────

def test_cjk_overlap_counts_shared_characters():
    assert _cjk_overlap("色即是空的梵文", "色即是空空即是色") == 4  # 色即是空
    assert _cjk_overlap("色即是空的梵文", "受想行识亦复如是") == 1  # 是
    assert _cjk_overlap("", "色即是空") == 0
    assert _cjk_overlap("rūpaṃ", "śūnyatā") == 0  # no CJK either side


def test_rank_prefers_query_relevant_sentence_over_higher_confidence():
    """The whole point: a 「受想行识」 sentence with HIGHER confidence must lose to
    the 「色即是空」 sentence the user actually asked about."""
    items = [
        {"lang": "sa", "chunk_text": "Evam eva vedanā", "zh_text": "受想行识亦复如是", "confidence": 0.99},
        {"lang": "sa", "chunk_text": "rūpaṃ śūnyatā", "zh_text": "色即是空空即是色", "confidence": 0.80},
    ]
    ranked = _rank_mitra_by_relevance(items, "《心经》「色即是空」的梵文是什么")
    assert ranked[0]["chunk_text"] == "rūpaṃ śūnyatā", "the query-relevant sentence must rank first"


def test_rank_falls_back_to_confidence_when_no_overlap():
    items = [
        {"lang": "sa", "chunk_text": "low", "zh_text": "毫不相关", "confidence": 0.40},
        {"lang": "bo", "chunk_text": "high", "zh_text": "另一无关", "confidence": 0.90},
    ]
    ranked = _rank_mitra_by_relevance(items, "色即是空")
    assert ranked[0]["chunk_text"] == "high"  # overlap tie (0) → confidence desc


# ── _attach_mitra_parallels (bulk) ────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_results_no_db_call():
    db = _make_db_with_rows([])
    results: list[dict] = []
    await _attach_mitra_parallels(db, results, "任意问题")
    assert db.execute.await_count == 0
    assert results == []


@pytest.mark.asyncio
async def test_single_bulk_query_ranks_relevant_sentence_first():
    primaries = [{"text_id": 100 + i, "juan_num": 1, "chunk_index": i} for i in range(3)]
    # primary 0 has two Sanskrit sentences; the 受想行识 one has higher confidence
    # but the query asks about 色即是空 — relevance must reorder them.
    rows = [
        (0, "sa", "Evam eva vedanā", "受想行识亦复如是", 0.99),
        (0, "sa", "rūpaṃ śūnyatā", "色即是空空即是色", 0.80),
        (2, "sa", "prajñā", "般若", 0.60),
    ]
    db = _make_db_with_rows(rows)
    await _attach_mitra_parallels(db, primaries, "「色即是空」的梵文原文")
    assert db.execute.await_count == 1, "must be a single bulk query"
    assert primaries[0]["mitra_parallels"][0]["chunk_text"] == "rūpaṃ śūnyatā"
    assert primaries[1]["mitra_parallels"] == []
    assert primaries[2]["mitra_parallels"][0]["lang"] == "sa"


@pytest.mark.asyncio
async def test_db_error_is_swallowed():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0}]
    await _attach_mitra_parallels(db, primaries, "问题")  # must not raise
    assert primaries[0]["mitra_parallels"] == []


# ── _format_context_block rendering ───────────────────────────────────

def _result(**over):
    base = {
        "text_id": 1, "juan_num": 1, "chunk_index": 0,
        "chunk_text": "汉文正文", "title_zh": "心經", "cbeta_id": "T0251", "score": 0.9,
    }
    base.update(over)
    return base


def test_mitra_only_renders_in_block():
    r = _result(mitra_parallels=[{"lang": "sa", "chunk_text": "prajñā", "confidence": 0.9}])
    out = _format_context_block(r)
    assert "[跨藏对读 parallel_chunks]" in out
    assert "[梵] (MITRA 对读): prajñā" in out
    assert "汉文正文" in out


def test_mitra_dedups_language_already_covered_by_alignment_pairs():
    r = _result(
        parallel_chunks=[{"lang": "bo", "chunk_text": "藏文对读", "juan_num": 2, "title": "甘珠尔"}],
        mitra_parallels=[
            {"lang": "bo", "chunk_text": "mitra tibetan dup", "confidence": 0.9},
            {"lang": "sa", "chunk_text": "mitra sanskrit new", "confidence": 0.8},
        ],
    )
    out = _format_context_block(r)
    assert "《甘珠尔》 第2卷: 藏文对读" in out          # alignment_pairs bo kept
    assert "mitra tibetan dup" not in out              # duplicate bo skipped
    assert "[梵] (MITRA 对读): mitra sanskrit new" in out  # new sa added


def test_mitra_render_capped():
    many = [{"lang": lang, "chunk_text": f"txt-{lang}", "confidence": 0.5} for lang in ("sa", "bo", "en", "pi")]
    r = _result(mitra_parallels=many)
    out = _format_context_block(r)
    rendered = out.count("(MITRA 对读)")
    assert rendered == MITRA_PARALLEL_SHOW, f"expected {MITRA_PARALLEL_SHOW} MITRA lines, got {rendered}"


def test_no_parallels_is_unchanged():
    r = _result()
    out = _format_context_block(r)
    assert "[跨藏对读" not in out
    assert out.endswith("汉文正文")
