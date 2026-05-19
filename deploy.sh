#!/usr/bin/env bash
#
# fojin 生产部署脚本 —— 幂等、路径感知、带健康检查。
#
#   用法:  ./deploy.sh [branch]      (branch 默认 master)
#
# 设计要点 (踩过的坑都在这里固化下来):
#   - 不用 `git pull`: VPS 上多个本地 feature 分支会触发
#     "Cannot fast-forward to multiple branches"。改用 fetch + 显式 ff-merge。
#   - 后端代码走 bind-mount, uvicorn 无 --reload: `docker compose up -d`
#     不会重建未变镜像的容器, 新代码不会被加载。必须显式 `restart backend`。
#   - 路径感知: 只重建/重启真正改动的服务, 避免每次全量 build 攒构建缓存。
#   - 部署后做真实健康检查, 不是 `sleep 10` 了事。
#
set -euo pipefail

BRANCH="${1:-master}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

log()  { printf '\n\033[1;36m>>> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m!!! %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. 取最新代码 -----------------------------------------------------------
log "Fetching origin/$BRANCH ..."
OLD_REV="$(git rev-parse HEAD)"
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH" \
  || fail "ff-merge 失败 — 工作区可能有本地提交或未提交改动, 请人工处理。"
NEW_REV="$(git rev-parse HEAD)"

if [ "$OLD_REV" = "$NEW_REV" ]; then
  log "已是最新 ($(git rev-parse --short HEAD)) — 无需部署。"
  exit 0
fi
log "HEAD: $(git rev-parse --short "$OLD_REV") -> $(git rev-parse --short "$NEW_REV")"

# --- 2. 判断改了哪些服务 -----------------------------------------------------
CHANGED="$(git diff --name-only "$OLD_REV" "$NEW_REV")"
echo "$CHANGED" | sed 's/^/    /'

frontend_changed=false
backend_changed=false
backend_image_changed=false
if echo "$CHANGED" | grep -q '^frontend/'; then frontend_changed=true; fi
if echo "$CHANGED" | grep -q '^backend/';  then backend_changed=true;  fi
if echo "$CHANGED" | grep -qE '^backend/(Dockerfile|requirements[^/]*\.txt|pyproject\.toml)$'; then
  backend_image_changed=true
fi

# --- 3. 前端: 改了就重建镜像 + 重建容器 --------------------------------------
if $frontend_changed; then
  log "Frontend changed — building image + recreating container ..."
  docker compose build frontend
  docker compose up -d frontend
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
    log "Backend code changed — restarting container (bind-mount reload) ..."
    docker compose restart backend
  fi
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
