"""Tests for alignment coverage aggregation.

The SQL is Postgres-native (array_agg, ::numeric — like the alignment catalog),
so the coverage arithmetic + ranking is tested via the pure helpers and the
db.execute call is mocked with Row-like objects.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.alignment_coverage import (
    _coverage_pct,
    _shape_row,
    _sort_key,
    compute_alignment_coverage,
)


def test_coverage_pct_basic_and_rounding():
    assert _coverage_pct(1, 4) == 25.0
    assert _coverage_pct(1, 3) == 33.3  # rounded to 1dp
    assert _coverage_pct(4, 4) == 100.0


def test_coverage_pct_unknown_total_is_none():
    assert _coverage_pct(3, 0) is None
    assert _coverage_pct(0, -1) is None


def test_coverage_pct_caps_at_100_for_stale_juan_refs():
    # An alignment can cite a juan beyond what text_contents knows (stale import);
    # that must not read as >100% covered.
    assert _coverage_pct(5, 3) == 100.0


def _row(**kw):
    base = dict(
        lzh_id=1, title_zh="经", dynasty="唐", pair_count=10, aligned_juans=2,
        total_juans=8, avg_confidence=0.9, partner_langs=["bo"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_shape_row_computes_remaining_and_coverage():
    out = _shape_row(_row(aligned_juans=2, total_juans=8))
    assert out["remaining_juans"] == 6
    assert out["coverage_pct"] == 25.0
    assert out["partner_langs"] == ["bo"]
    assert out["avg_confidence"] == 0.9


def test_shape_row_unknown_total():
    out = _shape_row(_row(aligned_juans=3, total_juans=0))
    assert out["remaining_juans"] is None
    assert out["coverage_pct"] is None


def test_sort_ranks_biggest_actionable_gap_first():
    items = [
        {"remaining_juans": 2, "pair_count": 50},   # small gap
        {"remaining_juans": 20, "pair_count": 5},   # biggest gap → first
        {"remaining_juans": None, "pair_count": 99},  # unknown → last
        {"remaining_juans": 20, "pair_count": 30},  # tie on gap, more pairs → before the 5-pair one
    ]
    ordered = sorted(items, key=_sort_key)
    assert [i["remaining_juans"] for i in ordered] == [20, 20, 2, None]
    assert ordered[0]["pair_count"] == 30  # gap tie broken by pair_count desc


async def test_compute_alignment_coverage_shapes_and_sorts():
    rows = [
        _row(lzh_id=1, title_zh="心经", aligned_juans=1, total_juans=1, pair_count=8),
        _row(lzh_id=2, title_zh="法华经", aligned_juans=3, total_juans=28, pair_count=259),
    ]
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(all=lambda: rows)

    out = await compute_alignment_coverage(db, limit=200)
    # 法华经 has the bigger gap (25 remaining vs 0) → ranked first.
    assert [i["text_id"] for i in out] == [2, 1]
    assert out[0]["coverage_pct"] == round(3 / 28 * 100, 1)
    assert out[1]["coverage_pct"] == 100.0

    # limit is applied.
    assert len(await compute_alignment_coverage(db, limit=1)) == 1
