#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# PROVENANCE / 来源说明(本副本为版本控制 bus-factor,非从 repo 运行):
#   生产 VPS(sg-vps)上 *实际运行* 的"答案质量回归门"主机侧 cron 包装的忠实副本。
#   - 部署位置:host:/home/admin/fojin-eval-regression.sh(repo 目录之外,手动管理;
#     被 fojin-backup.sh 的 /home/admin/*.sh 通配自动纳入每日备份)
#   - 调度:admin crontab,建议每日(语料库只在 prod,门跑不进 GitHub CI)
#   - Telegram 凭据:走 host 环境(crontab 行内或 /home/admin/.env),**不在本脚本/repo 内**
#   - 修改逻辑须先改 host 再同步此副本(与 fojin-backup.sh 同约定)
#
# 职责(刻意做窄):跑容器内的回归门 → 仅失败时 Telegram 告警 → 透传退出码。
# 门的判定逻辑在 backend/eval/run_regression.sh(版本化)+ run_eval.py;
# metric 逻辑由 CI 单测(tests/test_retrieval_metrics.py 等)守。本包装的控制流
# 由 tests/test_eval_regression_wrapper.py 守(注入假 gate/假 curl,CI 跑)。
#
# 推荐 crontab 行(每日 04:10,设绝对下限 + 容器内对照 baseline):
#   10 4 * * * TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \
#     EVAL_GATE_CMD='docker compose exec -T -e MIN_RECALL5=0.30 backend eval/run_regression.sh' \
#     /home/admin/fojin-eval-regression.sh >> /home/admin/logs/eval-regression.log 2>&1
#
# 生成/更新 baseline(仅在 prod,有意的质量变更后):
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
