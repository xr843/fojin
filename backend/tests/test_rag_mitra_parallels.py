"""Tests for feeding MITRA parallels into the chat RAG context.

`mitra_alignments` (~908K Skt/Tib↔汉 sentence pairs, chunk-anchored on the 汉
side) was previously only surfaced in the reader panel. `_attach_mitra_parallels`
now also brings it to the answer side as an LLM-context-only `mitra_parallels`
field, and `_format_context_block` renders it in the [跨藏对读] block for
languages the small self-built alignment_pairs table didn't cover.

Asserts:
  1. _group_mitra_rows groups by primary + skips empty foreign_text (pure).
  2. _attach_mitra_parallels: one bulk query, populates mitra_parallels,
     empty input = no DB call, DB error is swallowed.
  3. _format_context_block: renders MITRA parallels, dedups languages already
     covered by alignment_pairs, caps at MITRA_PARALLEL_SHOW, and is unchanged
     when there are no MITRA parallels.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rag_retrieval import (
    MITRA_PARALLEL_SHOW,
    _attach_mitra_parallels,
    _format_context_block,
    _group_mitra_rows,
)


def _make_db_with_rows(rows):
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


# ── _group_mitra_rows (pure) ──────────────────────────────────────────

def test_group_mitra_rows_groups_and_skips_empty():
    # row shape: (primary_idx, foreign_lang, foreign_text, confidence)
    rows = [
        (0, "sa", "sanskrit A", 0.99),
        (0, "bo", "tibetan A", 0.90),
        (0, "sa", "", 0.80),          # empty foreign_text → skipped
        (2, "bo", "tibetan B", 0.70),
    ]
    grouped = _group_mitra_rows(rows)
    assert set(grouped.keys()) == {0, 2}
    assert [p["chunk_text"] for p in grouped[0]] == ["sanskrit A", "tibetan A"]
    assert grouped[0][0] == {"lang": "sa", "chunk_text": "sanskrit A", "confidence": 0.99}
    assert grouped[2][0]["lang"] == "bo"


# ── _attach_mitra_parallels (bulk) ────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_results_no_db_call():
    db = _make_db_with_rows([])
    results: list[dict] = []
    await _attach_mitra_parallels(db, results)
    assert db.execute.await_count == 0
    assert results == []


@pytest.mark.asyncio
async def test_single_bulk_query_populates_mitra_parallels():
    primaries = [{"text_id": 100 + i, "juan_num": 1, "chunk_index": i} for i in range(3)]
    rows = [
        (0, "sa", "sanskrit", 0.98),
        (0, "bo", "tibetan", 0.91),
        (2, "sa", "sanskrit c", 0.60),
    ]
    db = _make_db_with_rows(rows)
    await _attach_mitra_parallels(db, primaries)
    assert db.execute.await_count == 1, "must be a single bulk query"
    assert len(primaries[0]["mitra_parallels"]) == 2
    assert primaries[0]["mitra_parallels"][0]["chunk_text"] == "sanskrit"
    assert primaries[1]["mitra_parallels"] == []
    assert primaries[2]["mitra_parallels"][0]["lang"] == "sa"


@pytest.mark.asyncio
async def test_db_error_is_swallowed():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0}]
    await _attach_mitra_parallels(db, primaries)  # must not raise
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
    """If alignment_pairs already gave a Tibetan (bo) parallel, the MITRA
    Tibetan is skipped, but MITRA Sanskrit (sa) — which alignment_pairs lacks —
    is still added."""
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
