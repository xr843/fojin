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
  if echo "$BE_DIFF" | grep -q '^backend/'; then
    log "backend/ 自 ${BE_BASE:0:7} 起有变更 — 触发 restart。"
    echo "$BE_DIFF" | grep '^backend/' | sed 's/^/    /'
    backend_changed=true
    if echo "$BE_DIFF" | grep -qE '^backend/(Dockerfile|requirements[^/]*\.txt|pyproject\.toml)$'; then
      log "backend 依赖/Dockerfile 改动 — 升级为 rebuild image。"
      backend_image_changed=true
    fi
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
  log "无任何变更信号 (marker/.env/flag) — 无需部署。"
  exit 0
fi

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
    docker compose up -d backend
  else
    log "Backend code/env changed — restarting container (bind-mount reload) ..."
    docker compose restart backend
  fi
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
  echo "    注意: 入口文件 hash 可能不变, 确认前端真上线请抓一个 lazy chunk,"
  echo "          不要只凭首页 200 判断。"
fi

docker compose ps

# --- 6. 清理 (只清 dangling/构建缓存, 不碰运行中镜像) -------------------------
log "Pruning build cache + dangling images ..."
docker builder prune -f >/dev/null
docker image prune -f   >/dev/null

log "Done. Deployed $(git rev-parse --short HEAD) on $BRANCH."
