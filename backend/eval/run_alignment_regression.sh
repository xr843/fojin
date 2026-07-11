#!/usr/bin/env bash
# Alignment-quality regression gate — version-controlled for the same reason
# as run_regression.sh: changing run_alignment_eval's flags/signature must
# surface here in review, not silently break a cron that lives only on the VPS.
#
# Scoring uses --scores-from-db (the stores' own confidence / mitra_e_score
# columns), so this needs the corpus DB but no LLM/embedding API — cheap
# enough for a daily cron. It runs wherever that DB is reachable (prod cron
# via `docker compose exec -T backend eval/run_alignment_regression.sh`), NOT
# in CI. The metric LOGIC is unit-tested in CI (tests/test_alignment_metrics.py,
# tests/test_build_alignment_gold.py, tests/test_run_alignment_eval.py).
# Exits non-zero on regression; the thin prod wrapper (fojin-eval-regression.sh
# with EVAL_GATE_CMD pointing here) handles Telegram alerting.
#
# Usage (inside the backend container, cwd /app):
#   eval/run_alignment_regression.sh
#   ALIGN_GOLD=eval/alignment_gold.jsonl ALIGN_BASELINE=eval/reports/alignment-baseline-v2.json \
#     eval/run_alignment_regression.sh
#   MIN_PRECISION=0.90 TOLERANCE=0.03 eval/run_alignment_regression.sh
#   ALIGN_PREDICTIONS=/tmp/scores.jsonl eval/run_alignment_regression.sh   # scored file instead of DB columns
#
# Regenerate the baseline after an INTENDED quality change (then store the
# resulting raw json as the new ALIGN_BASELINE):
#   python -m eval.run_alignment_eval --gold "$ALIGN_GOLD" --scores-from-db --tag baseline
set -uo pipefail

GOLD="${ALIGN_GOLD:-eval/alignment_gold.jsonl}"
BASELINE="${ALIGN_BASELINE:-eval/reports/alignment-baseline.json}"
TOLERANCE="${TOLERANCE:-0.02}"

# Fail loudly on missing inputs. run_alignment_eval treats an unreadable
# --baseline as a gate failure only when --fail-on-regression is set, but a
# missing GOLD would crash anyway — say why, up front, in the alert tail.
if [ ! -f "$GOLD" ]; then
    echo "alignment regression gate: gold set not found: $GOLD" >&2
    echo "build + human-review one first: see eval/ALIGNMENT_EVAL.md" >&2
    exit 1
fi
if [ ! -f "$BASELINE" ]; then
    echo "alignment regression gate: baseline not found: $BASELINE" >&2
    echo "generate it first: python -m eval.run_alignment_eval --gold $GOLD --scores-from-db --tag baseline" >&2
    exit 1
fi

ARGS=(--gold "$GOLD" --baseline "$BASELINE" --fail-on-regression --regression-tolerance "$TOLERANCE")
if [ -n "${ALIGN_PREDICTIONS:-}" ]; then
    ARGS+=(--predictions "$ALIGN_PREDICTIONS")
else
    ARGS+=(--scores-from-db)
fi
[ -n "${MIN_PRECISION:-}" ] && ARGS+=(--min-precision "$MIN_PRECISION")
[ -n "${MIN_RECALL:-}" ] && ARGS+=(--min-recall "$MIN_RECALL")

exec python -m eval.run_alignment_eval "${ARGS[@]}"
