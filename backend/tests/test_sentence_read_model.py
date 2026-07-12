"""Tests for the sentence-level read model (services.get_sentence_parallels).

Phase 4 Package C. Like the chunk read model, the direction-agnostic folding
(the given text may sit on side A or side B of a sentence_alignments row) is
pushed into a single Postgres-native CASE query, so db.execute is mocked with
already-resolved row tuples and what's under test is:

  * the query is a single set-based call (no N+1) that is direction-agnostic
    (both text_a_id=:tid and text_b_id=:tid predicates + the a_is_src CASE) and
    ordered by the self side's char_start then similarity DESC (reading order);
  * resolved rows normalize into SentencePairRecord: self side echoes the query
    args, other side carries the counterpart id/juan/offsets/lang/title, both
    sides carry sub-paragraph char spans and verbatim sent_text;
  * NULL counterpart offsets propagate as None; similarity coerces to float and
    is_verified to bool;
  * an empty juan yields [].
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.alignment_read_model import SentencePairRecord, get_sentence_parallels


def _result(rows):
    r = MagicMock()
    r.fetchall.return_value = rows
    return r


def _db(*result_rows):
    """AsyncSession-like mock: each positional arg is the fetchall() row list of
    one successive db.execute call (this read model issues exactly one)."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(rows) for rows in result_rows])
    return db


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _executed_sql(db) -> str:
    return str(db.execute.await_args.args[0])


def _executed_params(db):
    return db.execute.await_args.args[1]


# Row shape of the resolved SELECT (self side already folded to the given text):
# (self_cs, self_ce, self_lang, self_text,
#  other_tid, other_juan, other_cs, other_ce, other_lang, other_text,
#  similarity, align_type, method, is_verified, other_title)
ROW_PI = (
    0, 40, "lzh", "如是我聞",
    200, 1, 0, 60, "pi", "Evaṃ me sutaṃ",
    0.95, "1-1", "sentence-bertalign", True, "Majjhima Nikāya",
)
# A row where the counterpart offsets are not backfilled yet (fallback path).
ROW_LZH = (
    41, 80, "lzh", "一時佛在舍衛國",
    300, 2, None, None, "lzh", "爾時世尊",
    0.80, "1-2", "manual", False, "別譯雜阿含經",
)


@pytest.mark.asyncio
async def test_single_set_based_query_is_direction_agnostic_and_reading_ordered():
    db = _db([ROW_PI, ROW_LZH])

    records = await get_sentence_parallels(db, 1, 5, limit=200)

    # One query only — the counterpart title is LEFT JOINed, not an N+1 lookup.
    assert db.execute.await_count == 1
    sql = _norm(_executed_sql(db))
    # Direction-agnostic: the given text is matched on BOTH sides, and a single
    # CASE folds each match to self vs other.
    assert "sa.text_a_id = :tid AND sa.text_a_juan_num = :juan" in sql
    assert "sa.text_b_id = :tid AND sa.text_b_juan_num = :juan" in sql
    assert "AS a_is_src" in sql
    # Reading order: self char_start asc, similarity desc as tiebreak.
    assert "ORDER BY r.self_cs, r.similarity DESC" in sql
    assert _executed_params(db) == {"tid": 1, "juan": 5, "limit": 200}

    # Python preserves the SQL-produced order.
    assert len(records) == 2
    assert [r.other_ref.text_id for r in records] == [200, 300]


@pytest.mark.asyncio
async def test_record_normalization_both_sides_and_spans():
    db = _db([ROW_PI])

    (rec,) = await get_sentence_parallels(db, 1, 5)

    # Self side echoes the query args and carries its own sub-paragraph span.
    assert rec.self_ref.text_id == 1 and rec.self_ref.juan_num == 5
    assert rec.self_ref.chunk_index is None  # sentence rows anchor on offsets
    assert rec.self_ref.lang == "lzh"
    assert (rec.self_ref.char_start, rec.self_ref.char_end) == (0, 40)
    assert rec.self_text == "如是我聞"
    # Other side carries the counterpart identity, span, lang, and title.
    assert rec.other_ref.text_id == 200 and rec.other_ref.juan_num == 1
    assert rec.other_ref.lang == "pi"
    assert (rec.other_ref.char_start, rec.other_ref.char_end) == (0, 60)
    assert rec.other_text == "Evaṃ me sutaṃ"
    assert rec.title == "Majjhima Nikāya"
    # Scalars.
    assert rec.similarity == 0.95 and isinstance(rec.similarity, float)
    assert rec.align_type == "1-1"
    assert rec.method == "sentence-bertalign"
    assert rec.is_verified is True
    assert isinstance(rec, SentencePairRecord)


@pytest.mark.asyncio
async def test_null_counterpart_offsets_propagate_and_bool_coercion():
    db = _db([ROW_LZH])

    (rec,) = await get_sentence_parallels(db, 1, 5)

    assert rec.other_ref.char_start is None and rec.other_ref.char_end is None
    assert rec.is_verified is False
    assert rec.align_type == "1-2" and rec.method == "manual"


@pytest.mark.asyncio
async def test_empty_juan_returns_empty_list():
    db = _db([])
    assert await get_sentence_parallels(db, 1, 5) == []
    assert db.execute.await_count == 1  # still a single query, no follow-ups


@pytest.mark.asyncio
async def test_limit_is_bound_into_query():
    db = _db([])
    await get_sentence_parallels(db, 7, 3, limit=50)
    assert _executed_params(db) == {"tid": 7, "juan": 3, "limit": 50}
