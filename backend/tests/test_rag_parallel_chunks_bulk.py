"""Tests for _attach_parallel_chunks bulk-fetch behavior.

Asserts:
  1. Only ONE db.execute call is made (was N+1: 1 alignment query per primary
     + 1 chunk-text fetch per parallel — up to 25 sequential awaits at 5×5).
  2. The function still populates parallel_chunks with the same shape as
     before for representative inputs.
  3. Empty input is a no-op (no DB call).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rag_retrieval import _attach_parallel_chunks


def _make_db_with_rows(rows):
    """Build an AsyncSession-like mock whose execute() returns an object with
    fetchall() yielding `rows`.
    """
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_empty_results_no_db_call():
    db = _make_db_with_rows([])
    results: list[dict] = []
    await _attach_parallel_chunks(db, results)
    assert db.execute.await_count == 0
    assert results == []


@pytest.mark.asyncio
async def test_single_bulk_query_for_multiple_primaries():
    """5 primaries × up to 5 parallels each used to be 5 + 25 = 30 awaits.
    Now must be exactly 1 await on db.execute."""
    primaries = [{"text_id": 100 + i, "juan_num": 1, "chunk_index": i, "score": 0.9} for i in range(5)]
    # Two parallels for primary 0, one for primary 2, none for the rest.
    # Tuple shape matches the SELECT in _attach_parallel_chunks:
    # (primary_idx, other_text_id, other_juan, other_chunk_idx, other_lang,
    #  confidence, chunk_text, title)
    fake_rows = [
        (0, 200, 1, 0, "pi", 0.95, "pali chunk a", "Pali Title"),
        (0, 300, 1, 0, "bo", 0.88, "tibetan chunk a", "Tib Title"),
        (2, 201, 1, 2, "pi", 0.77, "pali chunk b", "Pali Title 2"),
    ]
    db = _make_db_with_rows(fake_rows)

    await _attach_parallel_chunks(db, primaries)

    assert db.execute.await_count == 1, f"expected exactly 1 bulk query, got {db.execute.await_count}"
    assert len(primaries[0]["parallel_chunks"]) == 2
    assert primaries[0]["parallel_chunks"][0] == {
        "text_id": 200,
        "juan_num": 1,
        "chunk_index": 0,
        "chunk_text": "pali chunk a",
        "lang": "pi",
        "title": "Pali Title",
        "confidence": 0.95,
    }
    assert primaries[1]["parallel_chunks"] == []
    assert len(primaries[2]["parallel_chunks"]) == 1
    assert primaries[2]["parallel_chunks"][0]["chunk_text"] == "pali chunk b"
    assert primaries[3]["parallel_chunks"] == []
    assert primaries[4]["parallel_chunks"] == []


@pytest.mark.asyncio
async def test_skips_rows_with_null_chunk_text():
    """LEFT JOIN may yield null chunk_text — those rows must be skipped, not
    crash, and not produce a malformed parallel_chunk."""
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0, "score": 0.9}]
    fake_rows = [
        (0, 999, 1, 0, "pi", 0.5, None, ""),  # missing text_embedding row
        (0, 998, 1, 0, "bo", 0.4, "tibetan", "T"),
    ]
    db = _make_db_with_rows(fake_rows)
    await _attach_parallel_chunks(db, primaries)
    assert db.execute.await_count == 1
    assert len(primaries[0]["parallel_chunks"]) == 1
    assert primaries[0]["parallel_chunks"][0]["text_id"] == 998


@pytest.mark.asyncio
async def test_lang_falls_back_to_lzh_when_null():
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0, "score": 0.9}]
    fake_rows = [
        (0, 50, 2, 3, None, 0.6, "chunk", "Title"),
    ]
    db = _make_db_with_rows(fake_rows)
    await _attach_parallel_chunks(db, primaries)
    assert primaries[0]["parallel_chunks"][0]["lang"] == "lzh"


@pytest.mark.asyncio
async def test_exception_swallowed_no_propagation():
    """Original behavior: any DB error logs + swallows. Bulk version must
    preserve that contract."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0, "score": 0.9}]
    # Should not raise.
    await _attach_parallel_chunks(db, primaries)
    # parallel_chunks initialized to [] but never populated.
    assert primaries[0]["parallel_chunks"] == []
