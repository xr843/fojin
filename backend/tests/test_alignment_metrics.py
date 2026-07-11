"""Tests for deterministic alignment-quality metrics (eval/alignment_metrics.py).

Pure-logic tests: no DB, no LLM, no network. They pin down the measurement
tool that gates cross-canon alignment quality (P/R/F1, threshold sweep,
calibration, slices, regression detection) so the gate itself can't rot —
same contract as tests/test_retrieval_metrics.py.
"""

import pytest
from eval.alignment_metrics import (
    calibration_table,
    compute_alignment_metrics,
    detect_regressions,
    join_gold_scores,
    negative_slice_metrics,
    precision_recall_f1,
    predictions_to_map,
    slice_metrics,
    threshold_sweep,
    validate_gold_record,
)


def _record(record_id, label, *, pair_kind="zh-pi", source="alignment_pairs",
            negative_kind=None, label_source="human", granularity="chunk", score=None):
    r = {
        "record_id": record_id,
        "source": source,
        "source_row_id": 1,
        "granularity": granularity,
        "pair_kind": pair_kind,
        "side_a": {"text_id": 1, "juan_num": 1, "chunk_index": 0, "lang": "zh"},
        "side_b": {"text_id": 2, "juan_num": 1, "chunk_index": 3, "lang": "pi"},
        "label": label,
        "label_source": label_source,
        "negative_kind": negative_kind,
        "note": "",
    }
    if score is not None:
        r["score"] = score
    return r


# --- validate_gold_record ----------------------------------------------------

def test_validate_accepts_well_formed_record():
    assert validate_gold_record(_record("g1", True)) == []


def test_validate_accepts_inline_text_side():
    r = _record("g1", True, source="mitra_alignments")
    r["side_b"] = {"text": "kāye kāyānupassī", "lang": "pi"}
    assert validate_gold_record(r) == []


def test_validate_rejects_bad_enums_and_missing_fields():
    r = _record("g1", True)
    r["pair_kind"] = "zh-fr"
    assert any("pair_kind" in p for p in validate_gold_record(r))

    r = _record("g1", True)
    del r["label_source"]
    assert validate_gold_record(r) == ["missing field: label_source"]

    r = _record("g1", "yes")  # non-bool label
    assert any("label must be a bool" in p for p in validate_gold_record(r))


def test_validate_positive_with_negative_kind_is_invalid():
    r = _record("g1", True, negative_kind="shifted")
    assert any("negative_kind=null" in p for p in validate_gold_record(r))


def test_validate_side_needs_reference_or_text():
    r = _record("g1", True)
    r["side_b"] = {"lang": "pi"}
    assert any("side_b" in p for p in validate_gold_record(r))


# --- predictions_to_map ------------------------------------------------------

def test_predictions_map_drops_and_counts_invalid_rows():
    rows = [
        {"record_id": "a", "score": 0.9},
        {"record_id": "b", "score": 1.5},       # out of range
        {"record_id": "c", "score": "high"},    # non-numeric
        {"record_id": "d", "score": True},      # bool is not a score
        {"score": 0.5},                          # missing record_id
        {"record_id": "a", "score": 0.7},       # duplicate — last wins, counted
    ]
    scores, invalid = predictions_to_map(rows)
    assert scores == {"a": 0.7}
    assert invalid == 5


def test_predictions_map_accepts_boundary_scores():
    scores, invalid = predictions_to_map([
        {"record_id": "lo", "score": 0.0},
        {"record_id": "hi", "score": 1.0},
    ])
    assert scores == {"lo": 0.0, "hi": 1.0}
    assert invalid == 0


# --- precision_recall_f1 -----------------------------------------------------

def test_prf_basic_confusion_counts():
    rows = [
        _record("p1", True, score=0.9),    # tp
        _record("p2", True, score=0.5),    # fn
        _record("n1", False, score=0.8),   # fp
        _record("n2", False, score=0.1),   # tn
    ]
    m = precision_recall_f1(rows, threshold=0.75)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == pytest.approx(0.5)
    assert m["recall"] == pytest.approx(0.5)
    assert m["f1"] == pytest.approx(0.5)
    assert m["num_scored"] == 4


def test_prf_score_equal_to_threshold_counts_positive():
    rows = [_record("p1", True, score=0.75)]
    m = precision_recall_f1(rows, threshold=0.75)
    assert m["tp"] == 1 and m["fn"] == 0


def test_prf_unscored_rows_are_excluded_not_zeroed():
    rows = [_record("p1", True, score=0.9), _record("p2", True)]  # p2 unscored
    m = precision_recall_f1(rows, threshold=0.75)
    assert m["num_scored"] == 1
    assert m["recall"] == pytest.approx(1.0)  # denominator excludes the unscored positive


def test_prf_empty_denominators_are_none_not_zero():
    # Nothing predicted positive → precision None; no gold positives → recall None.
    only_low_negatives = [_record("n1", False, score=0.2)]
    m = precision_recall_f1(only_low_negatives, threshold=0.75)
    assert m["precision"] is None
    assert m["recall"] is None
    assert m["f1"] is None

    assert precision_recall_f1([], threshold=0.5)["precision"] is None


def test_prf_f1_zero_when_precision_and_recall_zero():
    rows = [_record("p1", True, score=0.1), _record("n1", False, score=0.9)]
    m = precision_recall_f1(rows, threshold=0.75)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0


# --- threshold_sweep ---------------------------------------------------------

def test_sweep_covers_default_grid_and_is_monotonic_in_predictions():
    rows = [
        _record("p1", True, score=0.9),
        _record("p2", True, score=0.6),
        _record("n1", False, score=0.3),
    ]
    sweep = threshold_sweep(rows)
    assert len(sweep) == 21
    assert sweep[0]["threshold"] == 0.0
    assert sweep[-1]["threshold"] == 1.0
    # Predicted-positive count can only shrink as the threshold rises.
    predicted = [s["tp"] + s["fp"] for s in sweep]
    assert predicted == sorted(predicted, reverse=True)
    # At 0.0 everything is predicted parallel; recall is total.
    assert sweep[0]["recall"] == pytest.approx(1.0)


def test_sweep_custom_thresholds():
    rows = [_record("p1", True, score=0.5)]
    sweep = threshold_sweep(rows, thresholds=(0.4, 0.6))
    assert [s["threshold"] for s in sweep] == [0.4, 0.6]
    assert sweep[0]["tp"] == 1 and sweep[1]["tp"] == 0


# --- calibration_table -------------------------------------------------------

def test_calibration_buckets_scores_and_keeps_empty_buckets():
    rows = [
        _record("a", True, score=0.95),
        _record("b", False, score=0.92),
        _record("c", True, score=0.05),
    ]
    table = calibration_table(rows, num_buckets=10)
    assert len(table) == 10  # empty buckets kept, stable shape
    top = table[9]
    assert top["count"] == 2 and top["positives"] == 1
    assert top["observed_precision"] == pytest.approx(0.5)
    bottom = table[0]
    assert bottom["count"] == 1 and bottom["observed_precision"] == pytest.approx(1.0)
    assert all(b["observed_precision"] is None for b in table[1:9])


def test_calibration_score_one_lands_in_last_bucket():
    table = calibration_table([_record("a", True, score=1.0)], num_buckets=10)
    assert table[9]["count"] == 1
    assert sum(b["count"] for b in table) == 1


def test_calibration_all_positive_single_bucket():
    # The mitra degenerate case: every score is the constant 1.0 import flag.
    rows = [_record(f"m{i}", True, score=1.0) for i in range(5)]
    table = calibration_table(rows, num_buckets=10)
    assert table[9]["count"] == 5
    assert table[9]["observed_precision"] == pytest.approx(1.0)
    assert all(b["count"] == 0 for b in table[:9])


def test_calibration_ignores_unscored_and_empty_input():
    table = calibration_table([_record("a", True)], num_buckets=4)
    assert all(b["count"] == 0 and b["observed_precision"] is None for b in table)
    assert len(calibration_table([], num_buckets=4)) == 4


def test_calibration_bucket_boundary_is_left_closed():
    # 0.1 with 10 buckets belongs to bucket [0.1, 0.2), not [0.0, 0.1).
    table = calibration_table([_record("a", True, score=0.1)], num_buckets=10)
    assert table[1]["count"] == 1 and table[0]["count"] == 0


# --- slices ------------------------------------------------------------------

def test_slice_metrics_by_pair_kind():
    rows = [
        _record("p1", True, pair_kind="zh-pi", score=0.9),
        _record("p2", True, pair_kind="zh-bo", score=0.2),
        _record("n1", False, pair_kind="zh-bo", score=0.9, negative_kind="shifted"),
    ]
    slices = slice_metrics(rows, threshold=0.75, field="pair_kind")
    assert set(slices) == {"zh-pi", "zh-bo"}
    assert slices["zh-pi"]["recall"] == pytest.approx(1.0)
    assert slices["zh-bo"]["recall"] == pytest.approx(0.0)
    assert slices["zh-bo"]["precision"] == pytest.approx(0.0)  # only the fp predicted
    assert slices["zh-bo"]["num_gold"] == 2


def test_slice_metrics_missing_field_grouped_not_dropped():
    row = _record("x", True, score=0.9)
    del row["pair_kind"]
    slices = slice_metrics([row], threshold=0.5, field="pair_kind")
    assert slices["(missing)"]["num_gold"] == 1


def test_negative_slice_reports_false_positive_rate_per_kind():
    rows = [
        _record("p1", True, score=0.9),  # positives are ignored here
        _record("n1", False, negative_kind="shifted", score=0.9),
        _record("n2", False, negative_kind="shifted", score=0.1),
        _record("n3", False, negative_kind="cross_text", score=0.2),
        _record("n4", False, negative_kind="cross_text"),  # unscored
    ]
    slices = negative_slice_metrics(rows, threshold=0.75)
    assert slices["shifted"]["false_positives"] == 1
    assert slices["shifted"]["false_positive_rate"] == pytest.approx(0.5)
    assert slices["cross_text"]["count"] == 2
    assert slices["cross_text"]["num_scored"] == 1
    assert slices["cross_text"]["false_positive_rate"] == pytest.approx(0.0)


def test_negative_slice_unscored_kind_rate_is_none():
    slices = negative_slice_metrics([_record("n1", False, negative_kind="shifted")], 0.75)
    assert slices["shifted"]["false_positive_rate"] is None


# --- compute_alignment_metrics ----------------------------------------------

def test_compute_full_report_shape_and_coverage():
    gold = [
        _record("p1", True),
        _record("p2", True),
        _record("n1", False, negative_kind="cross_text"),
    ]
    scores = {"p1": 0.9, "n1": 0.1}  # p2 unscored
    m = compute_alignment_metrics(gold, scores, threshold=0.75)
    assert m["num_gold"] == 3
    assert m["num_positive"] == 2 and m["num_negative"] == 1
    assert m["num_scored"] == 2
    assert m["num_missing_predictions"] == 1
    assert m["prediction_coverage"] == pytest.approx(2 / 3)
    assert m["precision"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)  # over scored positives only
    assert len(m["sweep"]) == 21
    assert len(m["calibration"]) == 10
    assert set(m["slices"]) == {"pair_kind", "source", "label_source", "negative_kind"}


def test_compute_empty_gold_is_all_none_not_zero():
    m = compute_alignment_metrics([], {}, threshold=0.75)
    assert m["num_gold"] == 0
    assert m["prediction_coverage"] is None
    assert m["precision"] is None and m["recall"] is None and m["f1"] is None


def test_join_gold_scores_attaches_none_for_unscored():
    rows = join_gold_scores([_record("a", True)], {})
    assert rows[0]["score"] is None


# --- detect_regressions --------------------------------------------------------

def test_detect_regressions_flags_drop_beyond_tolerance():
    current = {"threshold": 0.75, "precision": 0.80, "recall": 0.90, "f1": 0.85, "prediction_coverage": 1.0}
    baseline = {"threshold": 0.75, "precision": 0.90, "recall": 0.90, "f1": 0.90, "prediction_coverage": 1.0}
    regressions = detect_regressions(current, baseline, tolerance=0.02)
    assert any(r.startswith("precision") for r in regressions)
    assert any(r.startswith("f1") for r in regressions)
    assert not any(r.startswith("recall") for r in regressions)


def test_detect_regressions_within_tolerance_or_improved_pass():
    current = {"threshold": 0.75, "precision": 0.89, "recall": 0.95, "f1": 0.92, "prediction_coverage": 1.0}
    baseline = {"threshold": 0.75, "precision": 0.90, "recall": 0.90, "f1": 0.90, "prediction_coverage": 1.0}
    assert detect_regressions(current, baseline, tolerance=0.02) == []


def test_detect_regressions_coverage_drop_is_flagged():
    # Scoring quietly stops covering the negatives → precision looks perfect
    # while coverage collapses; the gate must catch the collapse.
    current = {"threshold": 0.75, "precision": 1.0, "recall": 1.0, "f1": 1.0, "prediction_coverage": 0.5}
    baseline = {"threshold": 0.75, "precision": 0.9, "recall": 0.9, "f1": 0.9, "prediction_coverage": 1.0}
    regressions = detect_regressions(current, baseline, tolerance=0.02)
    assert any("prediction_coverage" in r for r in regressions)


def test_detect_regressions_none_values_skipped_not_treated_as_zero():
    current = {"threshold": 0.75, "precision": None, "recall": 0.9, "f1": None, "prediction_coverage": 1.0}
    baseline = {"threshold": 0.75, "precision": 0.9, "recall": 0.9, "f1": 0.9, "prediction_coverage": 1.0}
    assert detect_regressions(current, baseline, tolerance=0.02) == []


def test_detect_regressions_threshold_mismatch_is_a_regression():
    current = {"threshold": 0.6, "precision": 0.95, "recall": 0.95, "f1": 0.95, "prediction_coverage": 1.0}
    baseline = {"threshold": 0.75, "precision": 0.9, "recall": 0.9, "f1": 0.9, "prediction_coverage": 1.0}
    regressions = detect_regressions(current, baseline, tolerance=0.02)
    assert any("threshold mismatch" in r for r in regressions)
