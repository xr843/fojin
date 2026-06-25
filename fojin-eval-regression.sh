#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# PROVENANCE / 部署拓扑(本文件即源头:版本化 + CI 受测,非 VPS 副本):
#   "答案质量回归门"的主机侧包装。门跑不进 GitHub CI(检索召回要打 2.84 亿字 +
#   67.8 万向量的 pgvector,只 prod 有),所以跑在 sg-vps cron。实际拓扑(2026-06-25 起):
#   - 本脚本随 repo 部署到 host:/home/admin/fojin/fojin-eval-regression.sh(deploy.sh 同步)
#   - cron(admin,每日 04:45)调 VPS-only 瘦 shim /home/admin/fojin-eval-gate.sh,该 shim
#     仅 source Telegram 凭据(导出 TELEGRAM_BOT_TOKEN/CHAT_ID,**凭据不在 repo 内**)后
#     exec 本脚本 —— 凭据留 host、逻辑留 repo。日志 /home/admin/fojin-eval-gate.log
#   - 改逻辑改本文件即可(随 deploy 生效);改 shim/凭据才需登 host
#
# 职责(刻意做窄):跑容器内的回归门 → 仅失败时 Telegram 告警 → 透传退出码。
# 门的判定逻辑在 backend/eval/run_regression.sh(版本化)+ run_eval.py;
# metric 逻辑由 CI 单测(tests/test_retrieval_metrics.py 等)守。本包装的控制流
# 由 tests/test_eval_regression_wrapper.py 守(注入假 gate/假 curl,CI 跑)。
#
# 设绝对下限(可选,默认只对照 baseline 抓回归):令 shim 或 crontab 注入
#   EVAL_GATE_CMD='docker compose exec -T -e MIN_RECALL5=0.30 backend eval/run_regression.sh'
# 生成/更新 baseline(仅 prod,有意的质量变更后;eval/ 是 bind mount,host repo 可见):
#   docker compose exec -T backend python -m eval.run_eval --no-llm --tag baseline
#   # 然后把产出的 raw json 存为容器内 eval/reports/baseline.json
# ─────────────────────────────────────────────────────────────────────────
set -uo pipefail

# Overridable for testing; prod defaults run the gate inside the backend container
# where the corpus DB (pgvector) is reachable.
GATE_CMD="${EVAL_GATE_CMD:-docker compose exec -T backend eval/run_regression.sh}"
TELEGRAM_API_BASE="${TELEGRAM_API_BASE:-https://api.telegram.org}"

cd "${FOJIN_DIR:-/home/admin/fojin}" || {
    echo "[$(date)] ERROR: cannot cd into FoJin dir; aborting" >&2
    exit 3
}

# Run the gate, capturing combined output so a regression's detail can ride along
# into the alert. Word-splitting GATE_CMD is intentional (it is a command line).
# shellcheck disable=SC2086
OUT=$($GATE_CMD 2>&1)
CODE=$?
echo "$OUT"

if [ "$CODE" -ne 0 ]; then
    echo "[$(date)] eval regression gate FAILED (exit ${CODE})"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
        TAIL=$(printf '%s' "$OUT" | tail -c 1500)
        if curl -fsS -m 20 -X POST \
            "${TELEGRAM_API_BASE}/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=🔴 FoJin 答案质量回归门失败 (exit ${CODE})

${TAIL}" >/dev/null; then
            echo "[$(date)] telegram alert sent"
        else
            echo "[$(date)] WARNING: telegram alert failed to send"
        fi
    else
        echo "[$(date)] WARNING: TELEGRAM_BOT_TOKEN/CHAT_ID unset — alert skipped"
    fi
fi

exit "$CODE"
