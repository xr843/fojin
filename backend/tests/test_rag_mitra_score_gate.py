"""Tests for the ``mitra_e_score`` quality gate on MITRA RAG parallels.

``_attach_mitra_parallels`` fetches a per-chunk candidate pool from
``mitra_alignments`` and re-ranks it by relevance to the question. The gate
adds a **NULL-PERMISSIVE** quality filter to that fetch: scored rows must clear
``MITRA_MIN_SCORE`` while unscored rows (the whole table until a prod backfill
runs) still flow — so enabling the gate before the backfill is a no-op and does
**not** regress the currently-live feature.

The filtering/ordering itself is done in Postgres (via the
``ix_mitra_align_chunk_escore`` partial index), so these tests (a) assert on the
generated CTE SQL — that it contains/omits the predicate and the right ORDER BY
per flag, and passes the ``:min_score`` bind — and (b) exercise the row flow
through a fake DB that *honours* the emitted predicate/params, proving the
score-gating semantics end-to-end without touching a live database.
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.rag_retrieval as rag
from app.services.rag_retrieval import MITRA_MIN_SCORE, _attach_mitra_parallels


# ── fakes ─────────────────────────────────────────────────────────────

def _make_scored_db(stored_rows):
    """A fake DB that emulates the SQL the gate emits against ``stored_rows``.

    ``stored_rows`` are 6-tuples mirroring the ``mitra_alignments`` columns the
    CTE reads, plus the score used only for gating::

        (primary_idx, foreign_lang, foreign_text, zh_text, confidence, e_score)

    On ``execute`` we inspect the SQL the code actually built: if it carries the
    ``mitra_e_score`` predicate we apply the NULL-PERMISSIVE gate using the
    ``:min_score`` the code bound, then order by score DESC NULLS LAST (id
    tiebreak) — otherwise (gate off) we keep every row and order by confidence
    DESC. The projection drops the score, returning the 5-col shape the real
    SELECT yields, so ``_group_mitra_rows`` sees exactly its production input.
    """
    db = MagicMock()

    def _execute(clause, params=None):
        sql = str(clause)
        gated = "mitra_e_score" in sql
        min_score = (params or {}).get("min_score")
        kept = []
        for row_id, row in enumerate(stored_rows):
            escore = row[5]
            if gated and escore is not None and escore < min_score:
                continue  # scored below threshold → dropped by the predicate
            kept.append((row_id, row))
        if gated:
            kept.sort(key=lambda ir: (ir[1][5] is None, -(ir[1][5] or 0.0), ir[0]))
        else:
            kept.sort(key=lambda ir: (-ir[1][4], ir[0]))
        rows = [(r[0], r[1], r[2], r[3], r[4]) for _, r in kept]  # drop e_score column
        result = MagicMock()
        result.fetchall.return_value = rows
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _executed_sql(db) -> str:
    return str(db.execute.await_args.args[0])


def _executed_params(db):
    args = db.execute.await_args.args
    return args[1] if len(args) > 1 else None


def _norm(s: str) -> str:
    """Collapse all runs of whitespace so string asserts survive reindentation."""
    return re.sub(r"\s+", " ", s).strip()


# ── SQL / bind assertions ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_on_emits_null_permissive_predicate_and_score_order():
    stored = [(0, "sa", "prajñā", "甲", 1.0, 0.9)]
    db = _make_scored_db(stored)
    await _attach_mitra_parallels(db, [{"text_id": 1, "juan_num": 1, "chunk_index": 0}], "无关xyz")

    assert db.execute.await_count == 1, "must remain a single bulk query"
    sql = _norm(_executed_sql(db))
    assert "AND (ma.mitra_e_score IS NULL OR ma.mitra_e_score >= :min_score)" in sql
    assert "ORDER BY ma.mitra_e_score DESC NULLS LAST, ma.id" in sql
    assert "ORDER BY ma.confidence DESC" not in sql  # window no longer ranks by confidence
    assert _executed_params(db) == {"min_score": MITRA_MIN_SCORE}


@pytest.mark.asyncio
async def test_gate_off_is_byte_for_byte_pre_gate_sql(monkeypatch):
    monkeypatch.setattr(rag, "ENABLE_MITRA_SCORE_GATE", False)
    stored = [(0, "sa", "prajñā", "甲", 1.0, 0.9)]
    db = _make_scored_db(stored)
    await _attach_mitra_parallels(db, [{"text_id": 1, "juan_num": 1, "chunk_index": 0}], "无关xyz")

    sql = _norm(_executed_sql(db))
    assert "mitra_e_score" not in sql  # no predicate, no score ordering
    assert "PARTITION BY p.idx ORDER BY ma.confidence DESC, ma.id" in sql
    assert _executed_params(db) == {}  # nothing to bind when the gate is off


# ── pre-backfill: no regression ───────────────────────────────────────

@pytest.mark.asyncio
async def test_pre_backfill_all_null_scores_all_pass():
    """Every row unscored (NULL) — the IS NULL branch lets them all through, so
    the attached parallels are identical to the pre-gate feature."""
    stored = [
        (0, "sa", "sanskrit A", "甲", 1.0, None),
        (0, "bo", "tibetan A", "乙", 1.0, None),
        (0, "pi", "pali A", "丙", 1.0, None),
    ]
    db = _make_scored_db(stored)
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0}]
    await _attach_mitra_parallels(db, primaries, "无关xyz")

    texts = [p["chunk_text"] for p in primaries[0]["mitra_parallels"]]
    assert set(texts) == {"sanskrit A", "tibetan A", "pali A"}, "unscored rows must not be dropped"


# ── mixed scores ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mixed_high_kept_low_dropped_null_passes():
    stored = [
        (0, "sa", "below-threshold", "甲", 1.0, 0.10),   # < MITRA_MIN_SCORE → dropped
        (0, "bo", "unscored", "乙", 1.0, None),           # NULL → still passes
        (0, "pi", "high-quality", "丙", 1.0, 0.90),       # >= threshold → kept
    ]
    db = _make_scored_db(stored)
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0}]
    await _attach_mitra_parallels(db, primaries, "无关xyz")

    texts = [p["chunk_text"] for p in primaries[0]["mitra_parallels"]]
    assert "high-quality" in texts
    assert "unscored" in texts       # NULL-permissive
    assert "below-threshold" not in texts, "sub-threshold scored row must be gated out"


# ── ordering ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scored_rows_precede_null_and_higher_scored_first():
    """Confidence is a constant 1.0 import flag in prod, so with a query that
    shares no CJK with any row the relevance re-rank is a no-op tie and the
    SQL's score ordering (higher first, NULLs last) is what surfaces."""
    stored = [
        (0, "bo", "unscored", "乙", 1.0, None),
        (0, "sa", "mid", "甲", 1.0, 0.50),
        (0, "pi", "top", "丙", 1.0, 0.90),
    ]
    db = _make_scored_db(stored)
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0}]
    await _attach_mitra_parallels(db, primaries, "无关xyz")

    order = [p["chunk_text"] for p in primaries[0]["mitra_parallels"]]
    assert order == ["top", "mid", "unscored"], "scored desc first, NULL last"


# ── gate disabled: original behaviour ─────────────────────────────────

@pytest.mark.asyncio
async def test_gate_disabled_does_not_filter_low_scores(monkeypatch):
    monkeypatch.setattr(rag, "ENABLE_MITRA_SCORE_GATE", False)
    stored = [
        (0, "sa", "low-conf", "甲", 0.5, 0.10),   # low score AND low confidence
        (0, "bo", "high-conf", "乙", 0.9, 0.90),
    ]
    db = _make_scored_db(stored)
    primaries = [{"text_id": 1, "juan_num": 1, "chunk_index": 0}]
    await _attach_mitra_parallels(db, primaries, "无关xyz")

    texts = [p["chunk_text"] for p in primaries[0]["mitra_parallels"]]
    assert "low-conf" in texts, "gate off must not drop a sub-threshold-score row"
    assert texts == ["high-conf", "low-conf"], "gate off keeps the confidence DESC ordering"
