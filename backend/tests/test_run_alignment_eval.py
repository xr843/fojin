"""Tests for eval/run_alignment_eval.py — the alignment-quality runner + gate.

Exercises the CLI in-process with tmp gold/prediction/baseline files and a
redirected reports dir. Pins the run_eval.py exit-code convention the cron
shim (fojin-eval-regression.sh) relies on: exit 1 on any gate failure
(regression / floor breach / unreadable baseline under --fail-on-regression),
exit 0 otherwise.
"""

import json

import pytest
from eval import run_alignment_eval
from eval.run_alignment_eval import compare_baseline, load_gold, main


def _gold_record(record_id, label, *, negative_kind=None, pair_kind="zh-pi"):
    return {
        "record_id": record_id,
        "source": "alignment_pairs",
        "source_row_id": None if record_id.startswith("neg-") else int(record_id.split("-")[-1]),
        "granularity": "chunk",
        "pair_kind": pair_kind,
        "side_a": {"text_id": 1, "juan_num": 1, "chunk_index": 0, "lang": "zh"},
        "side_b": {"text_id": 2, "juan_num": 1, "chunk_index": 3, "lang": "pi"},
        "label": label,
        "label_source": "human",
        "negative_kind": negative_kind,
        "note": "",
    }


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    monkeypatch.setattr(run_alignment_eval, "REPORTS_DIR", reports)
    return reports


@pytest.fixture
def gold_path(tmp_path):
    path = tmp_path / "gold.jsonl"
    _write_jsonl(path, [
        _gold_record("ap-1", True),
        _gold_record("ap-2", True),
        _gold_record("neg-shifted-ap-1+1", False, negative_kind="shifted"),
        _gold_record("neg-crosstext-ap-1-1", False, negative_kind="cross_text"),
    ])
    return path


@pytest.fixture
def good_predictions(tmp_path):
    path = tmp_path / "preds.jsonl"
    _write_jsonl(path, [
        {"record_id": "ap-1", "score": 0.95},
        {"record_id": "ap-2", "score": 0.85},
        {"record_id": "neg-shifted-ap-1+1", "score": 0.40},
        {"record_id": "neg-crosstext-ap-1-1", "score": 0.05},
    ])
    return path


# --- load_gold -----------------------------------------------------------------

def test_load_gold_rejects_invalid_record(tmp_path):
    path = tmp_path / "bad.jsonl"
    record = _gold_record("ap-1", True)
    record["pair_kind"] = "zh-fr"
    _write_jsonl(path, [record])
    with pytest.raises(ValueError, match="pair_kind"):
        load_gold(path)


def test_load_gold_rejects_duplicate_record_id(tmp_path):
    path = tmp_path / "dup.jsonl"
    _write_jsonl(path, [_gold_record("ap-1", True), _gold_record("ap-1", True)])
    with pytest.raises(ValueError, match="duplicate record_id"):
        load_gold(path)


def test_load_gold_rejects_broken_json_with_line_number(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"record_id": "ap-1"\n', encoding="utf-8")
    with pytest.raises(ValueError, match=":1:"):
        load_gold(path)


# --- happy path ------------------------------------------------------------------

def test_run_writes_report_and_exits_zero(reports_dir, gold_path, good_predictions, capsys):
    main(["--gold", str(gold_path), "--predictions", str(good_predictions), "--tag", "t1"])

    raws = list(reports_dir.glob("alignment-eval-*-t1.json"))
    mds = list(reports_dir.glob("alignment-eval-*-t1.md"))
    assert len(raws) == 1 and len(mds) == 1

    metrics = json.loads(raws[0].read_text(encoding="utf-8"))
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["prediction_coverage"] == 1.0
    assert metrics["threshold"] == 0.75

    report = mds[0].read_text(encoding="utf-8")
    assert "跨藏对齐质量评测报告 — t1" in report
    assert "shifted" in report and "cross_text" in report


def test_run_warns_on_missing_and_invalid_predictions(reports_dir, gold_path, tmp_path, capsys):
    preds = tmp_path / "partial.jsonl"
    _write_jsonl(preds, [
        {"record_id": "ap-1", "score": 0.9},
        {"record_id": "ap-2", "score": 7.0},  # invalid — out of range
    ])
    main(["--gold", str(gold_path), "--predictions", str(preds)])
    out = capsys.readouterr().out
    assert "1 条预测无效" in out
    assert "3/4 条黄金记录没有预测分" in out


# --- regression gate ---------------------------------------------------------------

def _baseline(path, **overrides):
    metrics = {
        "threshold": 0.75, "precision": 1.0, "recall": 1.0, "f1": 1.0,
        "prediction_coverage": 1.0,
    }
    metrics.update(overrides)
    path.write_text(json.dumps(metrics), encoding="utf-8")
    return path


def test_gate_passes_against_equal_baseline(reports_dir, gold_path, good_predictions, tmp_path, capsys):
    baseline = _baseline(tmp_path / "baseline.json")
    main([
        "--gold", str(gold_path), "--predictions", str(good_predictions),
        "--baseline", str(baseline), "--fail-on-regression",
    ])  # no SystemExit → exit 0
    assert "✓ 对齐质量指标无回归" in capsys.readouterr().out


def test_gate_fails_on_regression_beyond_tolerance(reports_dir, gold_path, tmp_path, capsys):
    # Current run: the shifted negative now scores above threshold → precision 2/3.
    preds = tmp_path / "worse.jsonl"
    _write_jsonl(preds, [
        {"record_id": "ap-1", "score": 0.95},
        {"record_id": "ap-2", "score": 0.85},
        {"record_id": "neg-shifted-ap-1+1", "score": 0.90},  # false positive
        {"record_id": "neg-crosstext-ap-1-1", "score": 0.05},
    ])
    baseline = _baseline(tmp_path / "baseline.json")
    with pytest.raises(SystemExit) as excinfo:
        main([
            "--gold", str(gold_path), "--predictions", str(preds),
            "--baseline", str(baseline), "--fail-on-regression",
        ])
    assert excinfo.value.code == 1
    assert "precision" in capsys.readouterr().out


def test_gate_tolerance_absorbs_small_drop(reports_dir, gold_path, tmp_path):
    preds = tmp_path / "slightly-worse.jsonl"
    _write_jsonl(preds, [
        {"record_id": "ap-1", "score": 0.95},
        {"record_id": "ap-2", "score": 0.85},
        {"record_id": "neg-shifted-ap-1+1", "score": 0.90},  # precision 2/3
        {"record_id": "neg-crosstext-ap-1-1", "score": 0.05},
    ])
    baseline = _baseline(tmp_path / "baseline.json", precision=0.68, f1=0.81, recall=1.0)
    # Drop 0.68 → 0.667 is within a 0.05 tolerance (as is f1 0.81 → 0.8).
    main([
        "--gold", str(gold_path), "--predictions", str(preds),
        "--baseline", str(baseline), "--fail-on-regression",
        "--regression-tolerance", "0.05",
    ])  # no SystemExit


def test_gate_regressions_reported_but_pass_without_fail_flag(
    reports_dir, gold_path, tmp_path, capsys
):
    preds = tmp_path / "worse.jsonl"
    _write_jsonl(preds, [
        {"record_id": "ap-1", "score": 0.2},
        {"record_id": "ap-2", "score": 0.2},
        {"record_id": "neg-shifted-ap-1+1", "score": 0.9},
        {"record_id": "neg-crosstext-ap-1-1", "score": 0.9},
    ])
    baseline = _baseline(tmp_path / "baseline.json")
    main(["--gold", str(gold_path), "--predictions", str(preds), "--baseline", str(baseline)])
    assert "⚠️" in capsys.readouterr().out  # reported, but exit 0 without --fail-on-regression


def test_gate_unreadable_baseline_fails_when_gating(
    reports_dir, gold_path, good_predictions, tmp_path, capsys
):
    # A baseline we could not read is not a baseline we passed (run_eval's
    # hard-learned rule) — with --fail-on-regression this must exit 1.
    with pytest.raises(SystemExit) as excinfo:
        main([
            "--gold", str(gold_path), "--predictions", str(good_predictions),
            "--baseline", str(tmp_path / "missing.json"), "--fail-on-regression",
        ])
    assert excinfo.value.code == 1
    assert "baseline 对照失败" in capsys.readouterr().out


def test_gate_unreadable_baseline_soft_without_fail_flag(
    reports_dir, gold_path, good_predictions, tmp_path, capsys
):
    main([
        "--gold", str(gold_path), "--predictions", str(good_predictions),
        "--baseline", str(tmp_path / "missing.json"),
    ])  # warns but exits 0, mirroring run_eval
    assert "baseline 对照失败" in capsys.readouterr().out


# --- absolute floors ------------------------------------------------------------------

def test_min_precision_floor_breach_exits_one(reports_dir, gold_path, tmp_path, capsys):
    preds = tmp_path / "preds.jsonl"
    _write_jsonl(preds, [
        {"record_id": "ap-1", "score": 0.95},
        {"record_id": "neg-shifted-ap-1+1", "score": 0.90},  # precision 0.5
    ])
    with pytest.raises(SystemExit) as excinfo:
        main(["--gold", str(gold_path), "--predictions", str(preds), "--min-precision", "0.9"])
    assert excinfo.value.code == 1
    assert "Precision" in capsys.readouterr().out


def test_min_precision_floor_met_exits_zero(reports_dir, gold_path, good_predictions):
    main([
        "--gold", str(gold_path), "--predictions", str(good_predictions),
        "--min-precision", "0.9", "--min-recall", "0.9",
    ])  # no SystemExit


def test_min_precision_unmeasurable_fails_loudly(reports_dir, gold_path, tmp_path, capsys):
    # Nothing scores above threshold → precision is None. A requested floor
    # with nothing to measure must fail, not silently pass (run_eval's rule
    # for misconfigured faithfulness floors).
    preds = tmp_path / "all-low.jsonl"
    _write_jsonl(preds, [{"record_id": "ap-1", "score": 0.1}])
    with pytest.raises(SystemExit) as excinfo:
        main(["--gold", str(gold_path), "--predictions", str(preds), "--min-precision", "0.5"])
    assert excinfo.value.code == 1
    assert "N/A" in capsys.readouterr().out


# --- compare_baseline ---------------------------------------------------------------

def test_compare_baseline_separates_error_from_no_regressions(tmp_path):
    current = {"threshold": 0.75, "precision": 1.0, "recall": 1.0, "f1": 1.0, "prediction_coverage": 1.0}

    regressions, error = compare_baseline(str(tmp_path / "nope.json"), current)
    assert regressions == [] and error is not None

    good = _baseline(tmp_path / "b.json")
    regressions, error = compare_baseline(str(good), current)
    assert regressions == [] and error is None

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    regressions, error = compare_baseline(str(corrupt), current)
    assert regressions == [] and error is not None
