#!/usr/bin/env bash
# Answer-quality regression gate — version-controlled so changing run_eval's
# flags/signature surfaces here in review instead of silently breaking a cron
# that lives only on the VPS.
#
# Full eval needs the 678K-vector corpus DB, so this runs wherever that DB is
# reachable (prod cron via `docker compose exec -T backend eval/run_regression.sh`),
# NOT in CI. The metric LOGIC is unit-tested in CI (tests/test_retrieval_metrics.py,
# tests/test_rag_rerank_merge.py) so the measurement tool itself can't rot.
# Exits non-zero on regression; the thin prod wrapper handles Telegram alerting
# (creds stay out of the repo).
#
# Usage (inside the backend container, cwd /app):
#   eval/run_regression.sh
#   BASELINE=eval/reports/baseline-v2.json eval/run_regression.sh
#   MIN_RECALL5=0.30 TOLERANCE=0.03 eval/run_regression.sh
#
# Regenerate the baseline after an INTENDED quality change (then commit/store
# the resulting raw json as the new BASELINE):
#   python -m eval.run_eval --no-llm --tag baseline
set -uo pipefail

BASELINE="${BASELINE:-eval/reports/baseline.json}"
TOLERANCE="${TOLERANCE:-0.02}"

# Fail loudly if the baseline is missing. run_eval treats an unreadable
# --baseline as a soft "[baseline 对照失败]" and still exits 0, so without this
# guard a fresh deploy with no baseline.json would make the gate silently pass
# forever — the exact "gate quietly stops working" failure this script exists to
# prevent. Generate one first: python -m eval.run_eval --no-llm --tag baseline
if [ ! -f "$BASELINE" ]; then
    echo "regression gate: baseline not found: $BASELINE" >&2
    echo "generate it first: python -m eval.run_eval --no-llm --tag baseline" >&2
    exit 1
fi

ARGS=(--no-llm --baseline "$BASELINE" --fail-on-regression --regression-tolerance "$TOLERANCE")
[ -n "${MIN_RECALL5:-}" ] && ARGS+=(--min-recall5 "$MIN_RECALL5")

exec python -m eval.run_eval "${ARGS[@]}"
