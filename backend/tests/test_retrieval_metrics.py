"""Tests for deterministic retrieval metrics (eval/retrieval_metrics.py).

These are pure-logic tests: no DB, no LLM, no network. They pin down the
measurement tool that gates answer-quality (Recall@K / Hit@K / MRR / Precision@K)
so the gate itself can't silently rot.
"""

import pytest
from eval.retrieval_metrics import (
    aggregate_by_type,
    aggregate,
    compute_metrics,
    compute_metrics_graded,
    detect_regressions,
    gold_entries,
    hit_at_k,
    mrr,
    normalize_title,
    precision_at_k,
    recall_at_k,
    retrieval_type,
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


# --- retrieval_type: 归属题 vs 段落题 ---------------------------------------
# The gold set conflates two questions a retriever answers differently:
# "which sutra IS this from" (attribution — a lookup) vs "show me a passage
# about X" (passage — a similarity search). Mixing them into one Recall@5
# hides which mechanism is failing, so they are bucketed and reported apart.

def test_retrieval_type_reads_annotation():
    assert retrieval_type({"retrieval_type": "attribution",
                           "reference_sources": ["心经"]}) == "attribution"
    assert retrieval_type({"retrieval_type": "passage",
                           "reference_sources": ["心经"]}) == "passage"


def test_retrieval_type_is_none_without_gold():
    # out-of-scope questions have no gold and must not land in either bucket
    assert retrieval_type({"id": "oos-001", "question": "今天天气怎么样？"}) is None


def test_retrieval_type_unspecified_when_gold_but_unannotated():
    # Deliberately NOT defaulted to "passage": an un-annotated question must
    # stay visible in the report instead of silently padding a bucket.
    assert retrieval_type({"reference_sources": ["杂阿含经"]}) == "unspecified"


# --- relevance grading: 正解 vs 等价可接受来源 -------------------------------
# relevance 2 = the canonical source the answer should cite;
# relevance 1 = an equally defensible alternative (e.g. 大乘广五蕴论 for 五蕴).
# Strict metrics count only 2; lenient counts 1 and 2.

def test_gold_entries_filters_by_min_relevance():
    q = {"gold_sources": [
        {"title": "般若波罗蜜多心经", "relevance": 2},
        {"title": "大乘广五蕴论", "relevance": 1},
    ]}
    assert len(gold_entries(q)) == 2                      # unchanged default
    assert len(gold_entries(q, min_relevance=2)) == 1
    assert gold_entries(q, min_relevance=2)[0]["title"] == normalize_title("般若波罗蜜多心经")
    assert len(gold_entries(q, min_relevance=1)) == 2


def test_reference_sources_are_relevance_2_so_strict_is_unchanged():
    q = {"reference_sources": ["杂阿含经", "中论"]}
    assert len(gold_entries(q, min_relevance=2)) == 2


# --- compute_metrics_graded: strict + lenient in one row --------------------

def _q(gold_sources, rtype="passage"):
    return {"gold_sources": gold_sources, "retrieval_type": rtype}


def test_graded_metrics_keep_strict_under_the_original_key_names():
    # Old baselines compare on `recall@5`/`hit@5`; those names must keep
    # meaning "strict" or every stored baseline silently changes meaning.
    q = _q([{"title": "心经", "relevance": 2}, {"title": "大乘广五蕴论", "relevance": 1}])
    m = compute_metrics_graded([("心经", None)], q)
    assert m["recall@5"] == 1.0          # strict: 1/1 canonical hit
    # Lenient recall is normalised by the STRICT count: the question needed one
    # good source and one was found. Dividing by the enlarged gold set instead
    # would make 宽松 score BELOW 严格 whenever equivalents are added, which
    # reads as a broken ruler.
    assert m["lenient_recall@5"] == 1.0
    assert m["hit@5"] == 1.0
    assert m["retrieval_type"] == "passage"


def test_graded_lenient_credits_an_equivalent_source_strict_rejects():
    q = _q([{"title": "心经", "relevance": 2}, {"title": "大乘广五蕴论", "relevance": 1}])
    m = compute_metrics_graded([("大乘广五蕴论", None)], q)
    assert m["recall@5"] == 0.0          # canonical source missed
    assert m["lenient_recall@5"] == 1.0  # but the equivalent fully covers it
    assert m["hit@5"] == 0.0
    assert m["lenient_hit@5"] == 1.0


def test_graded_metrics_none_when_no_gold():
    m = compute_metrics_graded([("心经", None)], {"id": "oos-001"})
    assert m["recall@5"] is None
    assert m["lenient_recall@5"] is None
    assert m["retrieval_type"] is None


# --- aggregate_by_type -----------------------------------------------------

def test_aggregate_by_type_buckets_and_skips_typeless_rows():
    rows = [
        {"retrieval_type": "attribution", "recall@5": 1.0, "hit@5": 1.0},
        {"retrieval_type": "attribution", "recall@5": 0.0, "hit@5": 0.0},
        {"retrieval_type": "passage", "recall@5": 0.5, "hit@5": 1.0},
        {"retrieval_type": None, "recall@5": None, "hit@5": None},
    ]
    out = aggregate_by_type(rows)
    assert out["attribution"]["recall@5"] == 0.5
    assert out["attribution"]["n"] == 2
    assert out["passage"]["recall@5"] == 0.5
    assert out["passage"]["n"] == 1
    assert None not in out and "None" not in out


# --- regression gate must also watch the lenient family --------------------

def test_detect_regressions_flags_lenient_drop():
    regs = detect_regressions({"lenient_recall@5": 0.30}, {"lenient_recall@5": 0.50})
    assert any("lenient_recall@5" in r for r in regs)


# --- advisory: 在范围内但不依赖特定典籍 --------------------------------------
# "初学佛应该先读哪些经典" has no canonical source. Forcing gold onto it would
# make the ruler lie again, but leaving it bare would be indistinguishable from
# a question someone forgot to annotate — so it is declared explicitly.

def test_advisory_is_declared_not_inferred_from_missing_gold():
    assert retrieval_type({"retrieval_type": "advisory", "id": "prac-011"}) == "advisory"
    # bare, undeclared, no gold → still None (out-of-scope or not yet annotated)
    assert retrieval_type({"id": "prac-011"}) is None


def test_advisory_questions_carry_no_retrieval_metrics():
    m = compute_metrics_graded([("心经", None)], {"retrieval_type": "advisory"})
    assert m["recall@5"] is None
    assert m["retrieval_type"] == "advisory"


def test_aggregate_by_type_keeps_advisory_bucket_countable():
    out = aggregate_by_type([
        {"retrieval_type": "advisory", "recall@5": None},
        {"retrieval_type": "advisory", "recall@5": None},
    ])
    assert out["advisory"]["n"] == 2
    assert "recall@5" not in out["advisory"]     # no numbers to average


def test_lenient_recall_is_never_below_strict_recall():
    # The property that makes the two columns readable side by side. Adding an
    # 等价来源 must never make the 宽松 number worse than the 严格 one.
    q = _q([{"title": "心经", "relevance": 2},
            {"title": "大乘广五蕴论", "relevance": 1},
            {"title": "阿毘达磨俱舍论", "relevance": 1}])
    for retrieved in ([("心经", None)], [("大乘广五蕴论", None)], [("楞伽经义疏", 1)]):
        m = compute_metrics_graded(retrieved, q)
        assert m["lenient_recall@5"] >= m["recall@5"], retrieved


def test_lenient_recall_caps_at_one():
    q = _q([{"title": "心经", "relevance": 2},
            {"title": "大乘广五蕴论", "relevance": 1}])
    m = compute_metrics_graded([("心经", None), ("大乘广五蕴论", None)], q)
    assert m["lenient_recall@5"] == 1.0
