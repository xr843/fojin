"""Run the cross-canon alignment-quality evaluation against a gold set.

Usage:
    cd backend
    # Predictions from a scoring run (JSONL of {"record_id", "score"}):
    python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl \
        --predictions /tmp/alignment_scores.jsonl

    # Prod convenience: score gold rows from the stores' own columns
    # (alignment_pairs.confidence / mitra_alignments.mitra_e_score /
    # text_relations.confidence). Constructed negatives have no DB row and
    # stay unscored — see eval/ALIGNMENT_EVAL.md for what that does and
    # doesn't measure.
    python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl --scores-from-db

    # Regression gate (same flags + exit-code convention as run_eval.py, so
    # the fojin-eval-regression.sh cron shim's alerting works unchanged):
    python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl \
        --scores-from-db --baseline eval/reports/alignment-baseline.json \
        --fail-on-regression --regression-tolerance 0.02
    python -m eval.run_alignment_eval --gold ... --scores-from-db --min-precision 0.90
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.alignment_metrics import (
    DEFAULT_THRESHOLD,
    DEFAULT_TOLERANCE,
    compute_alignment_metrics,
    detect_regressions,
    predictions_to_map,
    validate_gold_record,
)

EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR = EVAL_DIR / "reports"


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_num}: invalid JSON — {exc}") from exc
    return rows


def load_gold(path: Path) -> list[dict]:
    """Load + validate the gold JSONL; a malformed gold set fails loudly.

    A gate measuring against silently-dropped records is worse than one that
    crashes — the cron wrapper alerts on any non-zero exit either way.
    """
    records = load_jsonl(path)
    seen: set[str] = set()
    for i, record in enumerate(records, 1):
        problems = validate_gold_record(record)
        if problems:
            raise ValueError(f"{path} record {i} ({record.get('record_id')!r}): {problems}")
        if record["record_id"] in seen:
            raise ValueError(f"{path}: duplicate record_id {record['record_id']!r}")
        seen.add(record["record_id"])
    return records


# ---------------------------------------------------------------------------
# --scores-from-db: read the stores' own confidence columns (prod only)
# ---------------------------------------------------------------------------

async def fetch_scores_from_db(gold: list[dict]) -> list[dict]:
    """Prediction rows for gold records that reference a DB row.

    Score source per store:
      alignment_pairs   → confidence (LLM verifier confidence at build time)
      mitra_alignments  → mitra_e_score when the column exists (backfill in
                          progress), else confidence — which is a constant 1.0
                          import flag, so until the backfill lands mitra rows
                          are a degenerate all-1.0 slice; the calibration
                          table makes that visible rather than hiding it.
      text_relations    → confidence (SuttaCentral/Akanuma import confidence)

    Constructed negatives (source_row_id null) have no stored score by
    definition — the build pipeline never persisted its rejections — and are
    left unscored. The runner reports them via prediction_coverage.
    """
    from sqlalchemy import bindparam
    from sqlalchemy import text as sql_text

    from app.database import async_session

    ids_by_source: dict[str, list[int]] = {}
    for record in gold:
        row_id = record.get("source_row_id")
        if row_id is not None:
            ids_by_source.setdefault(record["source"], []).append(row_id)

    predictions: list[dict] = []
    async with async_session() as session:
        has_e_score = await _column_exists(session, "mitra_alignments", "mitra_e_score")
        if ids_by_source.get("mitra_alignments") and not has_e_score:
            print(
                "⚠️  mitra_alignments.mitra_e_score 尚未 backfill——mitra 行将全部按 "
                "confidence=1.0 计分（导入标志，非质量分），校准表会显示这一坍缩。"
            )
        queries = {
            "alignment_pairs": "SELECT id, confidence AS score FROM alignment_pairs WHERE id IN :ids",
            "mitra_alignments": (
                "SELECT id, mitra_e_score AS score FROM mitra_alignments WHERE id IN :ids"
                if has_e_score
                else "SELECT id, confidence AS score FROM mitra_alignments WHERE id IN :ids"
            ),
            "text_relations": "SELECT id, confidence AS score FROM text_relations WHERE id IN :ids",
        }
        prefixes = {"alignment_pairs": "ap", "mitra_alignments": "ma", "text_relations": "tr"}
        for source, ids in ids_by_source.items():
            stmt = sql_text(queries[source]).bindparams(bindparam("ids", expanding=True))
            rows = (await session.execute(stmt, {"ids": ids})).fetchall()
            for row_id, score in rows:
                if score is None:
                    continue  # e.g. mitra_e_score not yet backfilled for this row
                predictions.append({"record_id": f"{prefixes[source]}-{row_id}", "score": float(score)})
    return predictions


async def _column_exists(session, table: str, column: str) -> bool:
    from sqlalchemy import text as sql_text

    try:
        result = await session.execute(
            sql_text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        return result.first() is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _fmt(value: object, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if isinstance(value, int | float) else "N/A"


def generate_report(metrics: dict, tag: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    h = metrics["headline"]
    lines = [
        f"# 跨藏对齐质量评测报告{' — ' + tag if tag else ''}",
        "",
        f"**日期**: {now}",
        f"**黄金集**: {metrics['num_gold']} 条（正例 {metrics['num_positive']} / 负例 {metrics['num_negative']}）",
        f"**已计分**: {metrics['num_scored']}（覆盖率 {_fmt(metrics['prediction_coverage'])}，"
        f"缺预测 {metrics['num_missing_predictions']} 条）",
        f"**阈值**: {metrics['threshold']}",
        "",
        "## 总体（确定性，对照黄金标注）",
        "",
        "| 指标 | 值 |", "|------|-----|",
        f"| Precision | {_fmt(h['precision'])} |",
        f"| Recall | {_fmt(h['recall'])} |",
        f"| F1 | {_fmt(h['f1'])} |",
        f"| TP / FP / FN / TN | {h['tp']} / {h['fp']} / {h['fn']} / {h['tn']} |",
        "",
        "## 阈值扫描", "",
        "| 阈值 | P | R | F1 | 预测为平行 |", "|------|---|---|----|-----------|",
    ]
    for row in metrics["sweep"]:
        lines.append(
            f"| {row['threshold']:.2f} | {_fmt(row['precision'])} | {_fmt(row['recall'])} "
            f"| {_fmt(row['f1'])} | {row['tp'] + row['fp']} |"
        )

    lines += [
        "", "## 校准（预测分十分位 → 实测精确率）", "",
        "| 分数区间 | 条数 | 正例 | 实测精确率 |", "|----------|------|------|-----------|",
    ]
    for b in metrics["calibration"]:
        lines.append(
            f"| {b['low']:.1f}–{b['high']:.1f} | {b['count']} | {b['positives']} "
            f"| {_fmt(b['observed_precision'])} |"
        )

    lines += ["", "## 分片", ""]
    for slice_name, title in (
        ("pair_kind", "按语言对"),
        ("source", "按存储"),
        ("label_source", "按标注来源"),
    ):
        lines += [
            f"### {title}", "",
            "| 片 | 条数 | 已计分 | P | R | F1 |", "|----|------|--------|---|---|----|",
        ]
        for key, m in metrics["slices"][slice_name].items():
            lines.append(
                f"| {key} | {m['num_gold']} | {m['num_scored']} | {_fmt(m['precision'])} "
                f"| {_fmt(m['recall'])} | {_fmt(m['f1'])} |"
            )
        lines.append("")

    lines += [
        "### 负例（按构造方式 — 看的是误报率）", "",
        "| negative_kind | 条数 | 已计分 | 误报 | 误报率 |",
        "|---------------|------|--------|------|--------|",
    ]
    for key, m in metrics["slices"]["negative_kind"].items():
        lines.append(
            f"| {key} | {m['count']} | {m['num_scored']} | {m['false_positives']} "
            f"| {_fmt(m['false_positive_rate'])} |"
        )
    if not metrics["slices"]["negative_kind"]:
        lines.append("| （无负例——精确率不可信，先补负例） | — | — | — | — |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Baseline comparison (mirrors run_eval.compare_baseline)
# ---------------------------------------------------------------------------

def compare_baseline(
    baseline_path: str, current: dict, tolerance: float = DEFAULT_TOLERANCE
) -> tuple[list[str], str | None]:
    """Compare this run against a prior raw report JSON.

    Returns ``(regressions, error)`` — separate values because "baseline
    unreadable" must not be confused with "no regressions found" (run_eval
    learned this the hard way: the gate silently stopped gating).
    """
    try:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        return detect_regressions(current, baseline, tolerance), None
    except (OSError, ValueError, KeyError) as exc:
        return [], str(exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run cross-canon alignment-quality evaluation")
    parser.add_argument("--gold", required=True, help="Gold-set JSONL (see eval/ALIGNMENT_EVAL.md)")
    scores_source = parser.add_mutually_exclusive_group(required=True)
    scores_source.add_argument("--predictions", help="Predictions JSONL of {record_id, score}")
    scores_source.add_argument("--scores-from-db", action="store_true",
                               help="Score gold rows from the stores' own confidence columns "
                                    "(needs the corpus DB; constructed negatives stay unscored)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Operating threshold: score >= this ⇒ predicted parallel "
                             f"(default {DEFAULT_THRESHOLD}, matching build_alignments)")
    parser.add_argument("--tag", type=str, default="", help="Tag for the report")
    parser.add_argument("--baseline", type=str,
                        help="Prior raw report JSON to compare metrics against")
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="Exit non-zero if metrics regress vs --baseline")
    parser.add_argument("--regression-tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help=f"Allowed drop before a metric counts as a regression (default {DEFAULT_TOLERANCE})")
    parser.add_argument("--min-precision", type=float,
                        help="Exit non-zero if precision falls below this absolute floor")
    parser.add_argument("--min-recall", type=float,
                        help="Exit non-zero if recall falls below this absolute floor")
    args = parser.parse_args(argv)

    gold = load_gold(Path(args.gold))
    if args.predictions:
        prediction_rows = load_jsonl(Path(args.predictions))
    else:
        prediction_rows = asyncio.run(fetch_scores_from_db(gold))

    scores, invalid = predictions_to_map(prediction_rows)
    if invalid:
        print(f"⚠️  {invalid} 条预测无效（缺 record_id / 分数非数值或超出 [0,1] / record_id 重复），已忽略")

    metrics = compute_alignment_metrics(gold, scores, threshold=args.threshold)
    if metrics["num_missing_predictions"]:
        print(
            f"⚠️  {metrics['num_missing_predictions']}/{metrics['num_gold']} 条黄金记录没有预测分"
            "——它们不进混淆矩阵。若缺的是负例（--scores-from-db 的构造负例无库内分数），"
            "本次 precision 只反映『存量分数 vs 正例』的校准，不反映真实精确率。"
        )

    report = generate_report(metrics, tag=args.tag)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag_suffix = f"-{args.tag}" if args.tag else ""
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"alignment-eval-{timestamp}{tag_suffix}.md"
        report_path.write_text(report, encoding="utf-8")
        raw_path = REPORTS_DIR / f"alignment-eval-{timestamp}{tag_suffix}.json"
        raw_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = f"\nReport: {report_path}\nRaw: {raw_path}"
    except OSError as exc:
        # Same failure mode as run_eval: in prod eval/reports is a host bind
        # mount owned by admin(1000) while the container runs app(999); an
        # unwritable dir must degrade loudly, not silently lose the future
        # --baseline.
        fallback = Path("/tmp")
        report_path = fallback / f"alignment-eval-{timestamp}{tag_suffix}.md"
        report_path.write_text(report, encoding="utf-8")
        raw_path = fallback / f"alignment-eval-{timestamp}{tag_suffix}.json"
        raw_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = (
            f"\n⚠️  {REPORTS_DIR} 不可写（{exc}）——报告写到了 EPHEMERAL 的 /tmp，"
            f"容器重启即丢失。\n    修复：chgrp 999 backend/eval/reports && chmod g+w backend/eval/reports"
            f"\nReport: {report_path}\nRaw: {raw_path}"
        )

    print(f"\n{'=' * 60}")
    print(report)
    print(saved)

    # Regression gate — same exit-code convention as run_eval.py (exit 1 on
    # any gate failure) so the cron shim's alerting works unchanged.
    gate_failed = False

    if args.baseline:
        regressions, error = compare_baseline(args.baseline, metrics, args.regression_tolerance)
        print(f"\n{'=' * 60}\n回归检查（对照 {args.baseline}）：")
        if error is not None:
            # An unreadable baseline is not a passed baseline (see run_eval).
            print(f"  ⚠️  [baseline 对照失败] {error}")
            if args.fail_on_regression:
                gate_failed = True
        elif regressions:
            for reg in regressions:
                print(f"  ⚠️  {reg}")
            if args.fail_on_regression:
                gate_failed = True
        else:
            print("  ✓ 对齐质量指标无回归")

    for flag_val, key, label in (
        (args.min_precision, "precision", "Precision"),
        (args.min_recall, "recall", "Recall"),
    ):
        if flag_val is None:
            continue
        value = metrics.get(key)
        # A floor with nothing to measure (e.g. zero scored negatives makes
        # precision None) fails loudly rather than silently passing.
        if not isinstance(value, int | float) or value < flag_val:
            shown = f"{value:.3f}" if isinstance(value, int | float) else "N/A（本次不可测）"
            print(f"\n  ⚠️  {label} {shown} 低于下限 {flag_val}")
            gate_failed = True

    if gate_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
