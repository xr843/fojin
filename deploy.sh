#!/usr/bin/env bash
#
# fojin 生产部署脚本 —— 幂等、路径感知、带健康检查。
#
#   用法:  ./deploy.sh [branch] [--force-frontend] [--force-backend]
#          branch 默认 master。flags 用于绕过自动判定。
#
# 设计要点 (踩过的坑都在这里固化下来):
#   - 不用 `git pull`: VPS 上多个本地 feature 分支会触发
#     "Cannot fast-forward to multiple branches"。改用 fetch + 显式 ff-merge。
#   - 后端代码走 bind-mount, uvicorn 无 --reload: `docker compose up -d`
#     不会重建未变镜像的容器, 新代码不会被加载。必须显式 `restart backend`。
#   - 路径感知: 只重建/重启真正改动的服务, 避免每次全量 build 攒构建缓存。
#   - .env 感知: frontend Dockerfile 把 VITE_* env 作为 ARG 烘焙进 bundle,
#     所以 .env 改动也要触发 frontend rebuild — git rev 没动 ≠ 无需部署。
#   - 部署后做真实健康检查, 不是 `sleep 10` 了事。
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

BRANCH=""
FORCE_FRONTEND=false
FORCE_BACKEND=false
for arg in "$@"; do
  case "$arg" in
    --force-frontend) FORCE_FRONTEND=true ;;
    --force-backend)  FORCE_BACKEND=true ;;
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
fail() { printf '\n\033[1;31m!!! %s\033[0m\n' "$*" >&2; exit 1; }

# True if reference file is missing or older than .env.
env_newer_than() {
  local marker="$1"
  [ -f .env ] || return 1
  [ ! -e "$marker" ] && return 0
  [ .env -nt "$marker" ]
}

# --- 1. 取最新代码 -----------------------------------------------------------
log "Fetching origin/$BRANCH ..."
OLD_REV="$(git rev-parse HEAD)"
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH" \
  || fail "ff-merge 失败 — 工作区可能有本地提交或未提交改动, 请人工处理。"
NEW_REV="$(git rev-parse HEAD)"

if [ "$OLD_REV" = "$NEW_REV" ]; then
  log "HEAD 未变 ($(git rev-parse --short HEAD)) — 仅按 .env / flag 判定是否仍要部署。"
else
  log "HEAD: $(git rev-parse --short "$OLD_REV") -> $(git rev-parse --short "$NEW_REV")"
fi

# --- 2. 综合判断改了哪些服务 -------------------------------------------------
CHANGED=""
if [ "$OLD_REV" != "$NEW_REV" ]; then
  CHANGED="$(git diff --name-only "$OLD_REV" "$NEW_REV")"
  echo "$CHANGED" | sed 's/^/    /'
fi

frontend_changed=false
backend_changed=false
backend_image_changed=false

if echo "$CHANGED" | grep -q '^frontend/'; then frontend_changed=true; fi
if echo "$CHANGED" | grep -q '^backend/';  then backend_changed=true;  fi
if echo "$CHANGED" | grep -qE '^backend/(Dockerfile|requirements[^/]*\.txt|pyproject\.toml)$'; then
  backend_image_changed=true
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

$FORCE_FRONTEND && { log "--force-frontend 已指定。"; frontend_changed=true; }
$FORCE_BACKEND  && { log "--force-backend 已指定。"; backend_changed=true; }

if ! $frontend_changed && ! $backend_changed; then
  log "无任何变更信号 (git/.env/flag) — 无需部署。"
  exit 0
fi

# --- 3. 前端: 改了就重建镜像 + 重建容器 --------------------------------------
if $frontend_changed; then
  log "Frontend changed — building image + recreating container ..."
  docker compose build frontend
  docker compose up -d frontend
  touch "$FRONTEND_BUILD_MARKER"
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
  touch "$BACKEND_RESTART_MARKER"
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
