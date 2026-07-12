"""Tests for the unified alignment read model (services/alignment_read_model).

The SQL is Postgres-native (CASE/CTE, DISTINCT ON, ANY) — like the alignment
catalog/coverage services — so db.execute is mocked with row tuples and the
merge + normalization logic is what's under test:

  * fojin pairs first (already ordered by SQL), then MITRA;
  * MITRA's constant confidence=1.0 tagged confidence_kind="import_flag",
    never as an "llm" quality score;
  * counterpart chunks that no longer exist are skipped (legacy parity);
  * char offsets from migration 0168 propagate into SegmentRef;
  * sutta-level records normalized from text_relations with
    confidence_kind="catalog" and no numeric confidence.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.alignment_read_model import (
    MITRA_CHUNK_LIMIT,
    get_chunk_parallels,
    get_text_parallels,
)


def _result(rows):
    r = MagicMock()
    r.fetchall.return_value = rows
    return r


def _db(*result_rows):
    """AsyncSession-like mock: each positional arg is the fetchall() row list
    of one successive db.execute call."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(rows) for rows in result_rows])
    return db


# Row shape of the pairs query:
# (other_tid, other_juan, other_cidx, other_lang, self_lang,
#  self_char_start, self_char_end, other_char_start, other_char_end,
#  confidence, method)
PAIR_PI = (200, 1, 4, "pi", "lzh", 10, 55, 0, 120, 0.95, "embed_llm")
PAIR_LZH = (300, 2, 7, "lzh", "lzh", None, None, None, None, 0.90, "manual")

# te rows: (text_id, juan_num, chunk_index, chunk_text, title)
TE_ROWS = [
    (200, 1, 4, "pali chunk (english tr)", "Majjhima Nikāya"),
    (300, 2, 7, "異譯漢文段", "別譯雜阿含經"),
]

# tc rows: (text_id, juan_num, lang, preview)
TC_ROWS = [(200, 1, "pi", "Evaṃ me sutaṃ ...")]

# mitra rows: (foreign_text, foreign_lang, confidence)
MITRA_ROWS = [("de bzhin gshegs pa ...", "bo", 1.0)]


@pytest.mark.asyncio
async def test_chunk_parallels_full_merge_order_and_normalization():
    db = _db([PAIR_PI, PAIR_LZH], TE_ROWS, TC_ROWS, MITRA_ROWS)

    records = await get_chunk_parallels(db, 1, 1, 0, limit=5)

    assert db.execute.await_count == 4  # pairs + te + tc + mitra, all set-based
    assert len(records) == 3
    # Order: fojin pairs in SQL order, then MITRA.
    assert [r.source for r in records] == ["embed_llm", "manual", "mitra"]

    pi = records[0]
    assert pi.granularity == "chunk"
    assert pi.confidence == 0.95
    assert pi.confidence_kind == "llm"
    assert pi.self_ref.text_id == 1 and pi.self_ref.chunk_index == 0
    assert pi.self_ref.lang == "lzh"
    assert (pi.self_ref.char_start, pi.self_ref.char_end) == (10, 55)
    assert pi.other_ref.text_id == 200 and pi.other_ref.chunk_index == 4
    assert (pi.other_ref.char_start, pi.other_ref.char_end) == (0, 120)
    assert pi.preview == "pali chunk (english tr)"
    assert pi.title == "Majjhima Nikāya"
    assert pi.original_preview == "Evaṃ me sutaṃ ..."
    assert pi.original_lang == "pi"

    lzh = records[1]
    assert lzh.source == "manual"
    assert lzh.original_preview is None and lzh.original_lang is None
    assert lzh.other_ref.char_start is None  # offsets not backfilled yet


@pytest.mark.asyncio
async def test_mitra_confidence_is_import_flag_not_llm_score():
    db = _db([], MITRA_ROWS)  # no pairs → te/tc queries skipped

    records = await get_chunk_parallels(db, 1, 1, 0, limit=5)

    assert db.execute.await_count == 2  # pairs + mitra only
    assert len(records) == 1
    m = records[0]
    assert m.source == "mitra"
    assert m.confidence == 1.0
    assert m.confidence_kind == "import_flag"  # the whole point: not "llm"
    assert m.other_ref.text_id is None  # inline foreign side, no fojin chunk
    assert m.other_ref.lang == "bo"
    assert m.preview == "de bzhin gshegs pa ..."
    assert m.self_ref.lang == "lzh"


@pytest.mark.asyncio
async def test_mitra_query_uses_its_own_cap_not_caller_limit():
    db = _db([], [])
    await get_chunk_parallels(db, 1, 1, 0, limit=3)
    mitra_call = db.execute.await_args_list[1]
    assert mitra_call.args[1]["limit"] == MITRA_CHUNK_LIMIT


@pytest.mark.asyncio
async def test_stale_counterpart_chunk_skipped():
    """A pair whose counterpart chunk vanished (stale positional ref) is
    dropped, exactly like the legacy endpoint did."""
    db = _db([PAIR_PI, PAIR_LZH], [TE_ROWS[1]], [], [])  # te row for 300 only

    records = await get_chunk_parallels(db, 1, 1, 0, limit=5)

    assert [r.other_ref.text_id for r in records] == [300]


@pytest.mark.asyncio
async def test_null_method_falls_back_and_unknown_method_passes_through():
    pair_null = PAIR_LZH[:10] + (None,)
    pair_fly = (301, 2, 8, "lzh", "lzh", None, None, None, None, 0.8, "flywheel-verified")
    te = [(300, 2, 7, "x", "t"), (301, 2, 8, "y", "t2")]
    db = _db([pair_null, pair_fly], te, [])

    records = await get_chunk_parallels(db, 1, 1, 0, limit=5)

    assert records[0].source == "embed_llm"  # NULL → default producer
    assert records[1].source == "flywheel-verified"  # unknown kept visible


@pytest.mark.asyncio
async def test_text_parallels_normalization_and_sort():
    rel_rows = [
        (20, "mention", None),         # lzh, no previews
        (10, "parallel", "full parallel"),  # pi, has previews
    ]
    meta_rows = [
        (10, "SC-mn10", "Satipaṭṭhānasutta", "pi"),
        (20, "T0100", "別譯雜阿含經", "lzh"),
    ]
    pali_rows = [(10, "Evaṃ me sutaṃ")]
    en_rows = [(10, "Thus have I heard")]
    db = _db(rel_rows, meta_rows, pali_rows, en_rows)

    records = await get_text_parallels(db, 1)

    assert db.execute.await_count == 4  # rels + meta + pali + en, set-based
    # 'parallel' relation sorts before others regardless of input order.
    assert [r.other_ref.text_id for r in records] == [10, 20]

    p = records[0]
    assert p.granularity == "sutta"
    assert p.source == "suttacentral"
    assert p.confidence is None
    assert p.confidence_kind == "catalog"  # no numeric score to compare
    assert p.self_ref.text_id == 1
    assert p.self_ref.juan_num is None and p.self_ref.chunk_index is None
    assert p.other_cbeta_id == "SC-mn10"
    assert p.title == "Satipaṭṭhānasutta"
    assert p.relation_type == "parallel" and p.note == "full parallel"
    assert p.preview == "Thus have I heard"
    assert p.original_preview == "Evaṃ me sutaṃ"
    assert p.original_lang == "pi"

    m = records[1]
    assert m.relation_type == "mention"
    assert m.preview is None and m.original_preview is None and m.original_lang is None


@pytest.mark.asyncio
async def test_text_parallels_missing_meta_skipped_and_empty_short_circuits():
    # Related text row vanished → record skipped (legacy parity).
    db = _db([(99, "parallel", None)], [], [], [])
    assert await get_text_parallels(db, 1) == []

    # No relations at all → single query, no follow-ups.
    db = _db([])
    assert await get_text_parallels(db, 1) == []
    assert db.execute.await_count == 1
