"""Tests for deterministic retrieval metrics (eval/retrieval_metrics.py).

These are pure-logic tests: no DB, no LLM, no network. They pin down the
measurement tool that gates answer-quality (Recall@K / Hit@K / MRR / Precision@K)
so the gate itself can't silently rot.
"""

import pytest
from eval.retrieval_metrics import (
    aggregate,
    compute_metrics,
    detect_regressions,
    gold_entries,
    hit_at_k,
    mrr,
    normalize_title,
    precision_at_k,
    recall_at_k,
    source_matches_gold,
    sources_to_pairs,
)

# --- normalize_title -------------------------------------------------------

def test_normalize_folds_traditional_to_simplified():
    assert normalize_title("般若波羅蜜多心經") == normalize_title("般若波罗蜜多心经")


def test_normalize_strips_book_brackets_and_whitespace():
    assert normalize_title("《杂阿含经》 ") == normalize_title("杂阿含经")


def test_normalize_strips_punctuation():
    assert normalize_title("心经·") == normalize_title("心经")


# --- gold_entries ----------------------------------------------------------

def test_gold_entries_from_reference_sources_are_title_level():
    q = {"reference_sources": ["般若波羅蜜多心經", "杂阿含经"]}
    entries = gold_entries(q)
    assert len(entries) == 2
    assert entries[0]["juan"] is None
    assert entries[0]["relevance"] == 2
    assert entries[0]["title"] == normalize_title("般若波罗蜜多心经")


def test_gold_entries_prefers_structured_gold_sources():
    q = {
        "reference_sources": ["杂阿含经"],
        "gold_sources": [{"title": "般若波罗蜜多心经", "juan": 1, "relevance": 3}],
    }
    entries = gold_entries(q)
    assert len(entries) == 1
    assert entries[0]["juan"] == 1
    assert entries[0]["relevance"] == 3
    assert entries[0]["title"] == normalize_title("般若波羅蜜多心經")


def test_gold_entries_empty_when_no_sources():
    assert gold_entries({"category": "out_of_scope"}) == []


# --- source_matches_gold ---------------------------------------------------

def test_match_is_traditional_simplified_insensitive():
    gold = {"title": normalize_title("心经"), "juan": None, "relevance": 2}
    assert source_matches_gold("般若波羅蜜多心經", 1, gold) is False  # different title
    assert source_matches_gold("心經", 7, gold) is True


def test_match_juan_none_matches_any_juan():
    gold = {"title": normalize_title("杂阿含经"), "juan": None, "relevance": 2}
    assert source_matches_gold("雜阿含經", 42, gold) is True


def test_match_specific_juan_must_equal():
    gold = {"title": normalize_title("杂阿含经"), "juan": 5, "relevance": 2}
    assert source_matches_gold("雜阿含經", 5, gold) is True
    assert source_matches_gold("雜阿含經", 6, gold) is False


# --- recall / hit / mrr / precision ---------------------------------------

def _gold(*titles_juans):
    return [
        {"title": normalize_title(t), "juan": j, "relevance": 2}
        for t, j in titles_juans
    ]


def test_recall_partial_within_k():
    retrieved = [("雜阿含經", 1), ("法華經", 1), ("心經", 1)]
    gold = _gold(("杂阿含经", None), ("中论", None))  # only 1 of 2 retrievable
    assert recall_at_k(retrieved, gold, 3) == pytest.approx(0.5)


def test_recall_respects_k_cutoff():
    retrieved = [("法華經", 1), ("心經", 1), ("雜阿含經", 1)]
    gold = _gold(("杂阿含经", None))
    assert recall_at_k(retrieved, gold, 2) == pytest.approx(0.0)  # match is at rank 3
    assert recall_at_k(retrieved, gold, 3) == pytest.approx(1.0)


def test_hit_at_k_is_binary():
    retrieved = [("法華經", 1), ("心經", 1)]
    gold = _gold(("心经", None))
    assert hit_at_k(retrieved, gold, 2) == 1.0
    assert hit_at_k(retrieved, gold, 1) == 0.0


def test_mrr_is_reciprocal_of_first_match_rank():
    retrieved = [("法華經", 1), ("雜阿含經", 1), ("心經", 1)]
    gold = _gold(("杂阿含经", None))
    assert mrr(retrieved, gold) == pytest.approx(0.5)  # first match at rank 2


def test_mrr_zero_when_no_match():
    retrieved = [("法華經", 1)]
    gold = _gold(("心经", None))
    assert mrr(retrieved, gold) == 0.0


def test_precision_at_k_fraction_relevant():
    retrieved = [("心經", 1), ("法華經", 1), ("雜阿含經", 1)]
    gold = _gold(("心经", None), ("杂阿含经", None))
    assert precision_at_k(retrieved, gold, 3) == pytest.approx(2 / 3)


def test_recall_never_exceeds_one_when_many_sources_hit_same_gold():
    # Two retrieved sources (same canon, different juan) both match one juan=None
    # gold entry — dedup must keep recall at 1.0, not double-count to 2.0.
    retrieved = [("心經", 1), ("心经", 7)]
    gold = _gold(("心经", None))
    assert recall_at_k(retrieved, gold, 5) == pytest.approx(1.0)


# --- compute_metrics -------------------------------------------------------

def test_compute_metrics_keys_and_none_when_no_gold():
    retrieved = [("心經", 1)]
    m = compute_metrics(retrieved, _gold(("心经", None)), ks=(1, 3))
    assert m["recall@1"] == pytest.approx(1.0)
    assert m["hit@1"] == 1.0
    assert m["mrr"] == pytest.approx(1.0)
    assert m["num_gold"] == 1
    assert m["num_retrieved"] == 1

    empty = compute_metrics(retrieved, [], ks=(1, 3))
    assert empty["recall@1"] is None
    assert empty["mrr"] is None
    assert empty["num_gold"] == 0


# --- aggregate -------------------------------------------------------------

def test_aggregate_means_and_skips_none():
    rows = [
        {"recall@1": 1.0, "mrr": 1.0, "num_gold": 1},
        {"recall@1": 0.0, "mrr": 0.5, "num_gold": 2},
        {"recall@1": None, "mrr": None, "num_gold": 0},  # no-gold row excluded
    ]
    agg = aggregate(rows)
    assert agg["recall@1"] == pytest.approx(0.5)
    assert agg["mrr"] == pytest.approx(0.75)


def test_aggregate_empty():
    assert aggregate([]) == {}


# --- detect_regressions ----------------------------------------------------

def test_detect_regressions_flags_drop_beyond_tolerance():
    current = {"recall@5": 0.70, "mrr": 0.60}
    baseline = {"recall@5": 0.80, "mrr": 0.60}
    regressions = detect_regressions(current, baseline, tolerance=0.02)
    assert any("recall@5" in r for r in regressions)
    assert not any("mrr" in r for r in regressions)


def test_detect_regressions_ignores_within_tolerance_and_improvement():
    current = {"recall@5": 0.79, "hit@1": 0.95}
    baseline = {"recall@5": 0.80, "hit@1": 0.80}
    assert detect_regressions(current, baseline, tolerance=0.02) == []


def test_detect_regressions_ignores_count_keys():
    current = {"num_retrieved": 3.0, "recall@5": 0.80}
    baseline = {"num_retrieved": 5.0, "recall@5": 0.80}
    assert detect_regressions(current, baseline, tolerance=0.02) == []


# --- sources_to_pairs ------------------------------------------------------

class _FakeSource:
    def __init__(self, title_zh, juan_num):
        self.title_zh = title_zh
        self.juan_num = juan_num


def test_sources_to_pairs_from_objects():
    sources = [_FakeSource("心經", 1), _FakeSource("法華經", 2)]
    assert sources_to_pairs(sources) == [("心經", 1), ("法華經", 2)]
