"""Deterministic alignment-quality metrics for the cross-canon eval harness.

The three alignment stores (``alignment_pairs`` / ``mitra_alignments`` /
``text_relations``) serve "parallel passages" the reader and RAG trust as
ground truth, yet their precision has only ever been eyeballed ("manually
verified on an MVP sample"). These functions add the *deterministic* layer:
given gold-labeled pairs (see eval/ALIGNMENT_EVAL.md for the JSONL format) and
predicted scores, compute precision/recall/F1 at a threshold, a full threshold
sweep, a calibration table (predicted-score deciles → observed precision), and
per-slice breakdowns (pair_kind / source store / negative_kind).

Pure logic only — no DB, no LLM, no network — so the metric layer is
unit-tested in CI (tests/test_alignment_metrics.py) while the full eval (which
needs prod stores to *produce* scores) runs on prod/cron. Mirrors the
conventions of eval/retrieval_metrics.py: metrics are ``None`` (not 0) when a
denominator is empty, aggregation skips ``None``, and ``detect_regressions``
gates only quality metrics.
"""

from __future__ import annotations

DEFAULT_THRESHOLD = 0.75  # matches scripts/build_alignments.py CONFIDENCE_THRESHOLD
DEFAULT_TOLERANCE = 0.02
DEFAULT_NUM_BUCKETS = 10
# 0.00, 0.05, …, 1.00 — fine enough to pick an operating point, coarse enough
# to eyeball in a Markdown table.
DEFAULT_SWEEP = tuple(round(i * 0.05, 2) for i in range(21))

PAIR_KINDS = ("zh-pi", "zh-bo", "zh-sa", "zh-en")
GRANULARITIES = ("chunk", "sutta")
LABEL_SOURCES = ("human", "seed_verified")
NEGATIVE_KINDS = ("shifted", "cross_text", "near_neighbor")
SOURCES = ("alignment_pairs", "mitra_alignments", "text_relations")

# detect_regressions only cares about quality metrics (plus prediction
# coverage — a gold set that silently loses its scored negatives would make
# precision look great while measuring nothing).
_GATED_KEYS = ("precision", "recall", "f1", "prediction_coverage")

_REQUIRED_FIELDS = (
    "record_id", "source", "granularity", "pair_kind",
    "side_a", "side_b", "label", "label_source", "negative_kind", "note",
)


def validate_gold_record(record: dict) -> list[str]:
    """Problems with one gold record; empty list means valid.

    Field-level validation only (enums, types, side shape) — cross-record
    checks (duplicate record_id) belong to the loader.
    """
    problems: list[str] = []
    for field in _REQUIRED_FIELDS:
        if field not in record:
            problems.append(f"missing field: {field}")
    if problems:
        return problems

    if not isinstance(record["record_id"], str) or not record["record_id"]:
        problems.append("record_id must be a non-empty string")
    if record["source"] not in SOURCES:
        problems.append(f"source must be one of {SOURCES}, got {record['source']!r}")
    if record["granularity"] not in GRANULARITIES:
        problems.append(f"granularity must be one of {GRANULARITIES}, got {record['granularity']!r}")
    if record["pair_kind"] not in PAIR_KINDS:
        problems.append(f"pair_kind must be one of {PAIR_KINDS}, got {record['pair_kind']!r}")
    if not isinstance(record["label"], bool):
        problems.append(f"label must be a bool, got {record['label']!r}")
    if record["label_source"] not in LABEL_SOURCES:
        problems.append(f"label_source must be one of {LABEL_SOURCES}, got {record['label_source']!r}")

    negative_kind = record["negative_kind"]
    if negative_kind is not None and negative_kind not in NEGATIVE_KINDS:
        problems.append(f"negative_kind must be null or one of {NEGATIVE_KINDS}, got {negative_kind!r}")
    if record["label"] is True and negative_kind is not None:
        problems.append("a positive (label=true) must have negative_kind=null")

    for side_name in ("side_a", "side_b"):
        side = record[side_name]
        if not isinstance(side, dict):
            problems.append(f"{side_name} must be an object")
            continue
        # A side is addressed by chunk/text reference OR carries inline text
        # (MITRA-style rows whose foreign side has no fojin chunk).
        if side.get("text_id") is None and not side.get("text"):
            problems.append(f"{side_name} needs a text_id reference or inline text")

    return problems


# ---------------------------------------------------------------------------
# Joining gold with predictions
# ---------------------------------------------------------------------------

def predictions_to_map(rows: list[dict]) -> tuple[dict[str, float], int]:
    """``[{record_id, score}]`` → ``(record_id→score, num_invalid)``.

    Invalid rows (missing record_id, non-numeric score, or score outside
    [0, 1]) are dropped and counted — silently clamping or zeroing them would
    hide a broken scorer from the gate. A duplicated record_id keeps the last
    score (JSONL append semantics) and counts the overwritten row as invalid.
    """
    scores: dict[str, float] = {}
    invalid = 0
    for row in rows:
        record_id = row.get("record_id")
        score = row.get("score")
        if (
            not isinstance(record_id, str)
            or not isinstance(score, int | float)
            or isinstance(score, bool)
            or not 0.0 <= score <= 1.0
        ):
            invalid += 1
            continue
        if record_id in scores:
            invalid += 1
        scores[record_id] = float(score)
    return scores, invalid


def join_gold_scores(gold: list[dict], scores: dict[str, float]) -> list[dict]:
    """Attach each gold record's predicted ``score`` (``None`` when unscored)."""
    return [{**record, "score": scores.get(record["record_id"])} for record in gold]


def _scored(rows: list[dict]) -> list[dict]:
    return [r for r in rows if isinstance(r.get("score"), int | float)]


# ---------------------------------------------------------------------------
# Precision / recall / F1 at a threshold
# ---------------------------------------------------------------------------

def precision_recall_f1(rows: list[dict], threshold: float) -> dict:
    """Confusion counts + P/R/F1 at ``score >= threshold`` ⇒ predicted parallel.

    Only scored rows enter the confusion matrix (an unscored record predicts
    nothing). Ratios with an empty denominator are ``None``, mirroring
    retrieval_metrics' no-gold convention, so aggregation and gating never
    mistake "unmeasured" for 0.
    """
    scored = _scored(rows)
    tp = sum(1 for r in scored if r["label"] and r["score"] >= threshold)
    fp = sum(1 for r in scored if not r["label"] and r["score"] >= threshold)
    fn = sum(1 for r in scored if r["label"] and r["score"] < threshold)
    tn = sum(1 for r in scored if not r["label"] and r["score"] < threshold)

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "num_scored": len(scored),
    }


def threshold_sweep(rows: list[dict], thresholds: tuple[float, ...] = DEFAULT_SWEEP) -> list[dict]:
    """P/R/F1 at every cut — the curve an operating threshold is picked from."""
    return [precision_recall_f1(rows, t) for t in thresholds]


# ---------------------------------------------------------------------------
# Calibration: does a stored confidence of 0.9 mean 90% precision?
# ---------------------------------------------------------------------------

def calibration_table(rows: list[dict], num_buckets: int = DEFAULT_NUM_BUCKETS) -> list[dict]:
    """Bucket predicted scores into ``num_buckets`` equal bins → observed precision.

    Bucket ``i`` covers ``[i/n, (i+1)/n)``; the last bucket is closed on the
    right so a score of exactly 1.0 lands in it instead of overflowing. Empty
    buckets are kept (``observed_precision=None``) so the table always has a
    stable shape and a score distribution collapsed onto one bucket is visible.
    """
    buckets = [
        {
            "low": round(i / num_buckets, 4),
            "high": round((i + 1) / num_buckets, 4),
            "count": 0,
            "positives": 0,
            "observed_precision": None,
        }
        for i in range(num_buckets)
    ]
    for r in _scored(rows):
        index = min(int(r["score"] * num_buckets), num_buckets - 1)
        buckets[index]["count"] += 1
        if r["label"]:
            buckets[index]["positives"] += 1
    for b in buckets:
        if b["count"]:
            b["observed_precision"] = b["positives"] / b["count"]
    return buckets


# ---------------------------------------------------------------------------
# Slice breakdowns
# ---------------------------------------------------------------------------

def slice_metrics(rows: list[dict], threshold: float, field: str) -> dict[str, dict]:
    """P/R/F1 per distinct value of ``field`` (e.g. pair_kind, source).

    Slice keys appear in first-seen order; records missing the field are
    grouped under ``"(missing)"`` rather than dropped, so a malformed gold set
    can't silently shrink a slice.
    """
    groups: dict[str, list[dict]] = {}
    for r in rows:
        key = r.get(field) or "(missing)"
        groups.setdefault(key, []).append(r)
    out: dict[str, dict] = {}
    for key, group in groups.items():
        metrics = precision_recall_f1(group, threshold)
        metrics["num_gold"] = len(group)
        out[key] = metrics
    return out


def negative_slice_metrics(rows: list[dict], threshold: float) -> dict[str, dict]:
    """Per-``negative_kind`` breakdown over the negatives only.

    For a negative the interesting number is not recall but the
    false-positive rate: what fraction of this kind of known-non-parallel
    still scores above the operating threshold. ``shifted`` negatives (same
    text pair, off-by-one chunk) failing here is the classic "embedding recall
    can't tell adjacent chunks apart" failure mode.
    """
    negatives = [r for r in rows if r["label"] is False]
    groups: dict[str, list[dict]] = {}
    for r in negatives:
        key = r.get("negative_kind") or "(unspecified)"
        groups.setdefault(key, []).append(r)
    out: dict[str, dict] = {}
    for key, group in groups.items():
        scored = _scored(group)
        false_positives = sum(1 for r in scored if r["score"] >= threshold)
        out[key] = {
            "count": len(group),
            "num_scored": len(scored),
            "false_positives": false_positives,
            "false_positive_rate": (false_positives / len(scored)) if scored else None,
        }
    return out


# ---------------------------------------------------------------------------
# Full report + regression gate
# ---------------------------------------------------------------------------

def compute_alignment_metrics(
    gold: list[dict],
    scores: dict[str, float],
    threshold: float = DEFAULT_THRESHOLD,
    num_buckets: int = DEFAULT_NUM_BUCKETS,
) -> dict:
    """Everything the runner reports, as one plain dict (JSON-serializable).

    ``prediction_coverage`` is first-class: the gate watches it so a scoring
    pass that quietly stops covering (say) the negatives — leaving precision
    computed over positives only — reads as a regression, not a pass.
    """
    rows = join_gold_scores(gold, scores)
    scored = _scored(rows)
    headline = precision_recall_f1(rows, threshold)

    num_positive = sum(1 for r in rows if r["label"])
    return {
        "threshold": threshold,
        "num_gold": len(rows),
        "num_positive": num_positive,
        "num_negative": len(rows) - num_positive,
        "num_scored": len(scored),
        "num_missing_predictions": len(rows) - len(scored),
        "prediction_coverage": (len(scored) / len(rows)) if rows else None,
        "precision": headline["precision"],
        "recall": headline["recall"],
        "f1": headline["f1"],
        "headline": headline,
        "sweep": threshold_sweep(rows),
        "calibration": calibration_table(rows, num_buckets),
        "slices": {
            "pair_kind": slice_metrics(rows, threshold, "pair_kind"),
            "source": slice_metrics(rows, threshold, "source"),
            "label_source": slice_metrics(rows, threshold, "label_source"),
            "negative_kind": negative_slice_metrics(rows, threshold),
        },
    }


def detect_regressions(
    current: dict, baseline: dict, tolerance: float = DEFAULT_TOLERANCE
) -> list[str]:
    """Gated metrics that dropped from ``baseline`` by more than ``tolerance``.

    Same contract as eval.retrieval_metrics.detect_regressions: only quality
    keys are compared, a ``None`` on either side is skipped (unmeasured is not
    a drop to zero), and each regression renders as a human-readable line for
    the report / Telegram alert tail.
    """
    regressions: list[str] = []
    if (
        isinstance(current.get("threshold"), int | float)
        and isinstance(baseline.get("threshold"), int | float)
        and current["threshold"] != baseline["threshold"]
    ):
        regressions.append(
            f"threshold mismatch: current {current['threshold']} vs baseline "
            f"{baseline['threshold']} — comparison is apples-to-oranges; "
            "regenerate the baseline at the current threshold"
        )
    for key in _GATED_KEYS:
        cur_val = current.get(key)
        base_val = baseline.get(key)
        if not isinstance(cur_val, int | float) or not isinstance(base_val, int | float):
            continue
        if base_val - cur_val > tolerance:
            regressions.append(
                f"{key}: {cur_val:.3f} < baseline {base_val:.3f} (Δ {cur_val - base_val:+.3f})"
            )
    return regressions
