#!/usr/bin/env bash
#
# fojin 生产部署脚本 —— 幂等、路径感知、带健康检查。
#
#   用法:  ./deploy.sh [branch] [--force-frontend] [--force-backend] [--rebuild-backend]
#          branch 默认 master。flags 用于绕过自动判定。
#
# 设计要点 (踩过的坑都在这里固化下来):
#   - 不用 `git pull`: VPS 上多个本地 feature 分支会触发
#     "Cannot fast-forward to multiple branches"。改用 fetch + 显式 ff-merge。
#   - 后端代码走 bind-mount, uvicorn 无 --reload: `docker compose up -d`
#     不会重建未变镜像的容器, 新代码不会被加载。必须显式 `restart backend`。
#   - 后端依赖变更必须 rebuild image: bind-mount 只覆盖代码,
#     `requirements.txt` / `Dockerfile` 改动要重新构建 image 才生效。
#   - 路径感知: 只重建/重启真正改动的服务, 避免每次全量 build 攒构建缓存。
#   - .env 感知: frontend Dockerfile 把 VITE_* env 作为 ARG 烘焙进 bundle,
#     所以 .env 改动也要触发 frontend rebuild — git rev 没动 ≠ 无需部署。
#   - CD 抢跑感知: marker 不是空的 touch 文件, 而是上次成功 build/restart 时
#     的 commit hash。比较 "marker 里的 commit" vs "当前 HEAD" 来检测变更,
#     这样即便别的进程 (webhook CD / 手动 git pull) 已经把代码拉下来,
#     我们也能正确判断未部署的差量。
#   - 部署后做真实健康检查, 不是 `sleep 10` 了事。
#   - 部署身份与看门狗一致: /api/version 每请求重读 backend/.deploy-version.json。
#     判定"无需部署"时也要把身份推进到 HEAD, 否则 eval/tests/docs-only 合并
#     会让 scheduled smoke 的漂移看门狗误报 CD 停摆 (2026-07-10 事故)。
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

BRANCH=""
FORCE_FRONTEND=false
FORCE_BACKEND=false
REBUILD_BACKEND=false
for arg in "$@"; do
  case "$arg" in
    --force-frontend)  FORCE_FRONTEND=true ;;
    --force-backend)   FORCE_BACKEND=true ;;
    --rebuild-backend) REBUILD_BACKEND=true ;;
    -*) printf '!!! 未知参数: %s\n' "$arg" >&2; exit 2 ;;
    *)
      if [ -n "$BRANCH" ]; then
        printf '!!! 只能指定一个 branch (已是 %s, 又收到 %s)\n' "$BRANCH" "$arg" >&2
        exit 2
      fi
      BRANCH="$arg"
      ;;
  esac
done
BRANCH="${BRANCH:-master}"

STATE_DIR="$REPO_DIR/.deploy-state"
FRONTEND_BUILD_MARKER="$STATE_DIR/last-frontend-build"
BACKEND_RESTART_MARKER="$STATE_DIR/last-backend-restart"
DEPLOY_VERSION_FILE="$REPO_DIR/backend/.deploy-version.json"
mkdir -p "$STATE_DIR"

log()  { printf '\n\033[1;36m>>> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m!!! %s\033[0m\n' "$*" >&2; }
fail() { printf '\n\033[1;31m!!! %s\033[0m\n' "$*" >&2; exit 1; }

# True if reference file is missing or older than .env.
env_newer_than() {
  local marker="$1"
  [ -f .env ] || return 1
  [ ! -e "$marker" ] && return 0
  [ .env -nt "$marker" ]
}

# Read first line of marker file (the commit hash from last successful build).
# Returns "" if marker missing or empty.
marker_commit() {
  local f="$1"
  [ -s "$f" ] && head -n1 "$f" || true
}

# True iff $1 is a known git commit in this repo.
is_known_commit() {
  git rev-parse --verify --quiet "$1^{commit}" >/dev/null 2>&1
}

write_deploy_version_file() {
  local commit="$1"
  local version="${APP_VERSION:-3.0.0}"
  command -v python3 >/dev/null || fail "python3 不在 PATH — 无法写入部署版本文件。"
  python3 - "$DEPLOY_VERSION_FILE" "$commit" "$version" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
commit = sys.argv[2]
version = sys.argv[3]
path.write_text(
    json.dumps(
        {
            "app": "fojin",
            "version": version,
            "commit": commit,
            "commit_short": commit[:7],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
  log "Wrote deploy identity $(git rev-parse HEAD) -> backend/.deploy-version.json"
}

dispatch_deploy_success() {
  local commit="$1"
  local repo="${GITHUB_REPOSITORY:-xr843/fojin}"
  if ! command -v gh >/dev/null 2>&1; then
    warn "gh 不在 PATH — 跳过 deploy-success dispatch。"
    return 0
  fi
  gh api --method POST "repos/${repo}/dispatches" \
    -f event_type=deploy-success \
    -f "client_payload[branch]=${BRANCH}" \
    -f "client_payload[commit]=${commit}" \
    >/dev/null \
    || { warn "deploy-success dispatch 失败 — 部署已完成，但生产 smoke 未触发。"; return 0; }
  log "Triggered deploy-success smoke for ${repo}@${commit:0:7}."
}

# --- 0. 并发锁 ---------------------------------------------------------------
# 串行化 deploy.sh 的并发运行 (cron 与手动, 或两次手动): 两个并发的
# `docker compose build` 会在 RAM 受限的 VPS 上把 dockerd 推向 OOM。
# 注意: 仓外的 webhook CD 若不经由 deploy.sh, 必须自己也取这把同一文件锁
# ($STATE_DIR/deploy.lock) 才能完全堵住与它的竞争 — 否则只挡住 deploy.sh 自身。
# 非阻塞获取: 抢不到锁就干净退出 (另一个 deploy 已在处理同一份代码)。
# 但"干净退出"不能是无限期的: 若持锁者僵死 (卡住的 build、挂起的 docker),
# 每次 webhook 都会静默让出, CD 就无声停摆 (2026-07 事故的失败模式之一)。
# 持锁者把 "PID 时间戳" 写进 holder 文件; 竞争失败时检查锁龄, 超过 45min
# (正常 build ≤ ~20min) 就以非零退出报僵死, 让 deploy.log / webhook 侧变红。
# 锁文件本身的 mtime 不可用: 每个竞争者的 `exec 200>` 都会 touch 它。
DEPLOY_LOCK="$STATE_DIR/deploy.lock"
LOCK_HOLDER="$STATE_DIR/deploy.holder"
exec 200>"$DEPLOY_LOCK"
if ! flock -n 200; then
  holder="$(cat "$LOCK_HOLDER" 2>/dev/null || true)"
  holder_pid="${holder%% *}"
  holder_ts="${holder##* }"
  if [[ "$holder_ts" =~ ^[0-9]+$ ]] && (( $(date +%s) - holder_ts > 2700 )); then
    fail "deploy.lock 已被 PID ${holder_pid:-?} 持有超过 45min — 疑似僵死。请人工检查该进程 (kill 后重跑 deploy.sh)。"
  fi
  warn "另一个 deploy 正在运行 (PID ${holder_pid:-?}, lock: $DEPLOY_LOCK) — 退出，避免并发 build 触发 OOM。"
  exit 0
fi
echo "$$ $(date +%s)" > "$LOCK_HOLDER"

# --- 1. 取最新代码 -----------------------------------------------------------
log "Fetching origin/$BRANCH ..."
OLD_REV="$(git rev-parse HEAD)"
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH" \
  || fail "ff-merge 失败 — 工作区可能有本地提交或未提交改动, 请人工处理。"
NEW_REV="$(git rev-parse HEAD)"

if [ "$OLD_REV" = "$NEW_REV" ]; then
  log "HEAD 未动 ($(git rev-parse --short HEAD)) — 按 marker / .env / flag 判定剩余 diff。"
else
  log "HEAD: $(git rev-parse --short "$OLD_REV") -> $(git rev-parse --short "$NEW_REV")"
fi

# --- 2. 基于 marker 计算每个 service 的真实 diff ----------------------------
# 不再用 OLD_REV → NEW_REV: 那样会被 CD 抢跑绕过 (HEAD 已经在新 commit, ff-merge
# 报 "Already up to date", OLD_REV == NEW_REV, 但 marker 还停在更早的 commit)。
# 改成 "上次成功 build/restart 时记录的 commit" → NEW_REV, 才反映真实未部署量。

FE_BASE="$(marker_commit "$FRONTEND_BUILD_MARKER")"
BE_BASE="$(marker_commit "$BACKEND_RESTART_MARKER")"

frontend_changed=false
backend_changed=false
backend_image_changed=false

# Frontend
if [ -z "$FE_BASE" ]; then
  log "frontend 无 build 记录 — 触发首次构建。"
  frontend_changed=true
elif ! is_known_commit "$FE_BASE"; then
  warn "frontend marker 指向未知 commit ($FE_BASE) — 保险起见重建。"
  frontend_changed=true
elif [ "$FE_BASE" != "$NEW_REV" ]; then
  FE_DIFF="$(git diff --name-only "$FE_BASE" "$NEW_REV")"
  if echo "$FE_DIFF" | grep -q '^frontend/'; then
    log "frontend/ 自 ${FE_BASE:0:7} 起有变更 — 触发 rebuild。"
    echo "$FE_DIFF" | grep '^frontend/' | sed 's/^/    /'
    frontend_changed=true
  fi
fi

# Backend (code vs image-level changes are distinct)
if [ -z "$BE_BASE" ]; then
  log "backend 无 restart 记录 — 触发首次构建。"
  backend_changed=true
  backend_image_changed=true
elif ! is_known_commit "$BE_BASE"; then
  warn "backend marker 指向未知 commit ($BE_BASE) — 保险起见重建 image。"
  backend_changed=true
  backend_image_changed=true
elif [ "$BE_BASE" != "$NEW_REV" ]; then
  BE_DIFF="$(git diff --name-only "$BE_BASE" "$NEW_REV")"
  # Live API path: backend/ minus dirs that don't ride the uvicorn process.
  # - backend/scripts/   : CLI tools (build_alignments, build_works, audits, …)
  # - backend/tests/     : pytest fixtures / unit tests
  # - backend/tests_integration/ : real-ES integration tests (CI-only lane)
  # - backend/eval/      : RAG eval harness
  # - backend/alembic/   : migration files (apply via `alembic upgrade`, not restart)
  # Changing any of these MUST NOT bounce a running uvicorn — and, more importantly,
  # MUST NOT kill long-running scripts a developer has launched via `docker exec`.
  BE_LIVE_DIFF="$(echo "$BE_DIFF" | grep -E '^backend/' | grep -vE '^backend/(scripts|tests|tests_integration|eval|alembic)/' || true)"
  if [ -n "$BE_LIVE_DIFF" ]; then
    log "backend/ live-API 路径自 ${BE_BASE:0:7} 起有变更 — 触发 restart。"
    echo "$BE_LIVE_DIFF" | sed 's/^/    /'
    backend_changed=true
    if echo "$BE_LIVE_DIFF" | grep -qE '^backend/(Dockerfile|requirements[^/]*\.txt|pyproject\.toml)$'; then
      log "backend 依赖/Dockerfile 改动 — 升级为 rebuild image。"
      backend_image_changed=true
    fi
  elif echo "$BE_DIFF" | grep -q '^backend/'; then
    # Pure scripts/tests/eval/alembic change — log but don't restart.
    log "backend/ 仅有 scripts/tests/eval/alembic 改动 — 跳过 restart（不影响 uvicorn，也不杀正在跑的脚本）。"
    echo "$BE_DIFF" | grep '^backend/' | sed 's/^/    /'
    # Pure-migration changes still need applying: entrypoint.sh only runs
    # `alembic upgrade head` on container START, and we intentionally do NOT
    # restart here (would kill long-running `docker exec` scripts). Without
    # this, a migration-only PR (e.g. a new data source) deploys "successfully"
    # but the migration stays unapplied until some unrelated app/ change later
    # triggers a restart. `upgrade head` is idempotent — no-op if already at head.
    if echo "$BE_DIFF" | grep -q '^backend/alembic/'; then
      log "检测到 alembic 迁移改动 — 运行 alembic upgrade head（容器不重启）。"
      docker compose exec -T backend alembic upgrade head \
        || fail "alembic upgrade head 失败 — 迁移未应用，请人工处理。"
    fi
    # Still bump the marker so we don't keep re-evaluating the same untouched
    # diff every cron tick — otherwise the next deploy.sh run will see the same
    # `BE_DIFF` and re-log this skip message indefinitely.
    echo "$NEW_REV" > "$BACKEND_RESTART_MARKER"
  fi
fi

# .env 时间戳触发: frontend 镜像把 .env 烘焙进 bundle, backend 进程启动时读 env.
if env_newer_than "$FRONTEND_BUILD_MARKER"; then
  log ".env 比 frontend 上次构建新 — 触发 frontend rebuild。"
  frontend_changed=true
fi
if env_newer_than "$BACKEND_RESTART_MARKER"; then
  log ".env 比 backend 上次重启新 — 触发 backend restart。"
  backend_changed=true
fi

# Manual overrides
$FORCE_FRONTEND  && { log "--force-frontend 已指定。";  frontend_changed=true; }
$FORCE_BACKEND   && { log "--force-backend 已指定。";   backend_changed=true; }
$REBUILD_BACKEND && { log "--rebuild-backend 已指定。"; backend_changed=true; backend_image_changed=true; }

if ! $frontend_changed && ! $backend_changed; then
  # 走到这里意味着工作树已 ff 到 NEW_REV 且服务行为与之等价 (eval/tests/docs-only
  # 等非服务路径改动)。部署身份仍须推进: /api/version 每请求重读该文件 (bind-mount
  # 即时可见), 不推进的话 scheduled smoke 的漂移看门狗会把"故意不重启"误报成
  # "CD stalled" (2026-07-10)。此路径后续无 compose 步骤, 写在判定之后不会重演
  # 2026-07-05 "身份先于部署成功落盘" 的虚报事故。
  write_deploy_version_file "$NEW_REV"
  log "无任何变更信号 (marker/.env/flag) — 无需部署 (部署身份已同步到当前 HEAD)。"
  exit 0
fi

write_deploy_version_file "$NEW_REV"

# --- 3. 前端: 改了就重建镜像 + 重建容器 --------------------------------------
if $frontend_changed; then
  log "Frontend changed — building image + recreating container ..."
  docker compose build frontend
  docker compose up -d frontend
  echo "$NEW_REV" > "$FRONTEND_BUILD_MARKER"
else
  log "Frontend unchanged — skip."
fi

# --- 4. 后端: 代码走 bind-mount, 必须显式 restart 才能让 uvicorn 重载 --------
if $backend_changed; then
  if $backend_image_changed; then
    log "Backend deps/Dockerfile changed — rebuilding image ..."
    docker compose build backend
  fi
  # Zero-downtime rolling restart across BOTH replicas (backend + backend2,
  # behind nginx upstream fojin_backend = 8000+8001). Recreate one at a time,
  # --wait for healthy, so the other keeps serving → no 502 window. --no-deps
  # avoids touching pg/es/redis. backend first so it runs alembic before
  # backend2 (never two concurrent `alembic upgrade head`). force-recreate
  # also reloads bind-mounted code, covering the code-only-change case.
  log "Rolling-restart backend replicas (zero-downtime) ..."
  docker compose up -d --no-deps --force-recreate --wait backend
  docker compose up -d --no-deps --force-recreate --wait backend2
  echo "$NEW_REV" > "$BACKEND_RESTART_MARKER"
else
  log "Backend unchanged — skip."
fi

# --- 5. 健康检查 -------------------------------------------------------------
log "Waiting for backend /api/health ..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "    backend OK"
    break
  fi
  if [ "$i" -eq 30 ]; then fail "backend 健康检查超时 (60s)"; fi
  sleep 2
done

if $frontend_changed; then
  log "Verifying frontend ..."
  # `|| true` 收尾: docker compose port 失败时不让 set -e 在守卫之前先杀脚本。
  FE_PORT="$(docker compose port frontend 80 2>/dev/null | cut -d: -f2 || true)"
  if [ -z "$FE_PORT" ]; then fail "拿不到 frontend 端口映射"; fi
  for i in $(seq 1 15); do
    if curl -sf "http://localhost:${FE_PORT}/" >/dev/null 2>&1; then
      echo "    frontend OK (port ${FE_PORT})"
      break
    fi
    if [ "$i" -eq 15 ]; then fail "frontend 健康检查超时 (30s)"; fi
    sleep 2
  done
  # 自动断言取代"请手动抓 lazy chunk"提示 (2026-06 #706/#708 部署事故教训):
  # 首页 200 不等于新版上线 —— 必须验证 index 引用的资产真实可取、
  # 且容器内 locale 文件和本次部署的代码一致。
  FE_BASE="http://localhost:${FE_PORT}"

  # (a) index.html 引用的 entry JS 必须 200
  ENTRY_JS="$(curl -sf "${FE_BASE}/" | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' | head -1 || true)"
  if [ -z "$ENTRY_JS" ]; then fail "index.html 里找不到 entry JS 引用"; fi
  curl -sf "${FE_BASE}${ENTRY_JS}" >/dev/null || fail "entry JS 404: ${ENTRY_JS}"

  # (b) entry 引用的第一个 lazy chunk 也必须 200 (entry hash 不变时这才是真信号)
  LAZY_CHUNK="$(curl -sf "${FE_BASE}${ENTRY_JS}" | grep -oE '[A-Za-z0-9_-]+-[A-Za-z0-9_-]{8}\.js' | grep -v '^index-' | head -1 || true)"
  if [ -n "$LAZY_CHUNK" ]; then
    curl -sf "${FE_BASE}/assets/${LAZY_CHUNK}" >/dev/null || fail "lazy chunk 404: ${LAZY_CHUNK}"
    echo "    lazy chunk OK (${LAZY_CHUNK})"
  fi

  # (c) 容器内 en locale 的 key 数必须和本次部署的源码一致
  #     (#708 教训: 服务旧 translation.json 时新 key 全部静默回退中文)
  command -v python3 >/dev/null || fail "python3 不在 PATH — locale 断言无法执行"
  [ -f frontend/public/locales/en/translation.json ] || fail "repo 里找不到 en translation.json"
  REPO_EN_KEYS="$(python3 -c "import json;print(len(json.load(open('frontend/public/locales/en/translation.json'))))" 2>/dev/null || echo 0)"
  SERVED_EN_KEYS="$(curl -sf "${FE_BASE}/locales/en/translation.json" | python3 -c "import json,sys;print(len(json.load(sys.stdin)))" 2>/dev/null || echo -1)"
  if [ "$REPO_EN_KEYS" != "$SERVED_EN_KEYS" ]; then
    fail "en locale 不一致: repo=${REPO_EN_KEYS} keys, 容器返回=${SERVED_EN_KEYS} keys"
  fi
  echo "    locale OK (en ${SERVED_EN_KEYS} keys, 与 repo 一致)"
fi

docker compose ps

# --- 6. 清理 (只清 dangling/构建缓存, 不碰运行中镜像) -------------------------
log "Pruning build cache + dangling images ..."
docker builder prune -f >/dev/null
docker image prune -f   >/dev/null

dispatch_deploy_success "$NEW_REV"

log "Done. Deployed $(git rev-parse --short HEAD) on $BRANCH."
