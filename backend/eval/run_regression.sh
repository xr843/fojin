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
#   eval/run_regression.sh                          # 检索指标（便宜，秒级）
#   LLM=1 eval/run_regression.sh                    # 加上答案质量 + 引用忠实度（~50min）
#   BASELINE=eval/reports/baseline-v2.json eval/run_regression.sh
#   MIN_RECALL5=0.30 TOLERANCE=0.03 eval/run_regression.sh
#
# Regenerate the baseline after an INTENDED quality change (then commit/store
# the resulting raw json as the new BASELINE):
#   python -m eval.run_eval --no-llm --tag baseline
#
# ⚠️ 测试集版本变了必须重生成 baseline。gold 集一改，指标的含义就变了；run_eval
# 会比对每行的 test_set_version，版本不符直接报错而不是给出「无回归」的假象。
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

# The ruler itself is checked before it is used. A gold entry naming a text the
# corpus doesn't have is a permanent, unfixable miss that quietly drags every
# retrieval metric down — worse than a quality regression, because no amount of
# retrieval work can ever clear it. 《慈经》/《入菩萨行论》 sat in the gold set that
# way for months. Fail here rather than measure with a broken ruler.
if ! python -m eval.check_gold_reachable; then
    echo "regression gate: 黄金来源不可达，先修 test_set.json 或补语料" >&2
    exit 1
fi

# LLM=1 runs the full answer-quality + faithfulness eval (~35s/question, costs
# tokens). Default stays retrieval-only so the nightly gate is cheap — but then
# answer-quality and 引用忠实度 have NO automated consumer, which is how they went
# unmeasured from 2026-07-09. Flip this on in the cron to get them back.
if [ -n "${LLM:-}" ]; then
    # temperature 0: a faithfulness delta is unreadable through sampling noise.
    ARGS=(--temperature 0)
else
    ARGS=(--no-llm)
fi
ARGS+=(--baseline "$BASELINE" --fail-on-regression --regression-tolerance "$TOLERANCE")
[ -n "${MIN_RECALL5:-}" ] && ARGS+=(--min-recall5 "$MIN_RECALL5")

exec python -m eval.run_eval "${ARGS[@]}"
