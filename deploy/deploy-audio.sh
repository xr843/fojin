#!/usr/bin/env bash
# 把 build_audio.py 的产物部署到生产。**在开发机上跑**，不是在 VPS 上。
#
#   ./deploy/deploy-audio.sh            # 全流程
#   ./deploy/deploy-audio.sh --dry-run  # 只看会做什么
#   ./deploy/deploy-audio.sh --nginx    # 顺带同步 host nginx 配置并 reload
#
# 四步：
#   1) 产物 rsync 到生产仓库的 backend/out/ —— 该目录在 .gitignore:74 里，
#      写它不会弄坏下次 git pull 部署；且 ./backend:/app 是 bind mount，
#      容器里直接可见为 /app/out/。
#   2) 在 backend 容器里跑 import_audio.py 写库。
#   3) 只把 mp3 rsync 到 /srv/fojin/audio/ —— host nginx 的 location /audio/
#      从这里静态直出，不经容器也不经后端。
#   4) （可选）同步 host nginx 配置：deploy/host-nginx/ 是仓库副本，
#      CD **不会**自动同步到 /etc/nginx/，见 deploy/host-nginx/README.md。
#
# ⚠️ 迁移不用管：backend/entrypoint.sh 启动时就跑 alembic upgrade head，
#    deploy.sh 在纯 alembic 改动时也会单独跑一次。
set -euo pipefail

VPS="${FOJIN_VPS:-admin@100.67.232.7}"
# ⚠️ 这台 WSL 连 sg-vps 必须指定 KEX：默认的后量子 KEX 包超过代理隧道 MTU，
#    会卡在 SSH2_MSG_KEX_ECDH_REPLY。
SSH_OPTS="-o KexAlgorithms=curve25519-sha256"
REPO_OUT="/home/admin/fojin/backend/out/audio/"
STATIC_DIR="/srv/fojin/audio/"
LOCAL_OUT="backend/out/audio/"

DRY=""
DO_NGINX=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY="--dry-run" ;;
    --nginx)   DO_NGINX=1 ;;
    *) echo "未知参数: $a" >&2; exit 2 ;;
  esac
done

log() { printf '\n\033[1;36m>>> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m!!! %s\033[0m\n' "$*" >&2; exit 1; }

[ -d "$LOCAL_OUT" ] || fail "$LOCAL_OUT 不存在 —— 先跑 build_audio.py"
MP3S=$(find "$LOCAL_OUT" -name '*.mp3' | wc -l)
CUES=$(find "$LOCAL_OUT" -name '*.cues.json' | wc -l)
[ "$MP3S" -gt 0 ] || fail "$LOCAL_OUT 下没有 mp3"
[ "$MP3S" -eq "$CUES" ] || fail "mp3($MP3S) 与 cues.json($CUES) 数量不符 —— 产物不完整"
log "本地产物：$MP3S 个 mp3 / $CUES 份 cues"

log "① 产物 → 生产仓库 backend/out/（gitignored，容器内可见）"
# ⚠️ /srv 是 root 所有（drwxr-xr-x root:root），直接 mkdir 会 Permission denied。
#    用 install -d 一次性建好并把属主给部署账号，后续 rsync 才写得进去；
#    755 保证 nginx 的 worker 进程读得到。
ssh $SSH_OPTS "$VPS" "mkdir -p $REPO_OUT &&
  sudo install -d -o \$(id -un) -g \$(id -gn) -m 755 /srv/fojin $STATIC_DIR"
# 只传 mp3 与 cues.json，**不传 *.parts/**（逐句 WAV 分片，几百个大文件）
rsync -av $DRY --include='*/' --include='*.mp3' --include='*.cues.json' \
  --exclude='*' --prune-empty-dirs -e "ssh $SSH_OPTS" \
  "$LOCAL_OUT" "$VPS:$REPO_OUT"

log "② 容器内入库（先 dry-run 看一眼）"
ssh $SSH_OPTS "$VPS" "cd /home/admin/fojin && docker compose exec -T backend \
  python -m scripts.audio.import_audio --dir out/audio --dry-run"
if [ -z "$DRY" ]; then
  ssh $SSH_OPTS "$VPS" "cd /home/admin/fojin && docker compose exec -T backend \
    python -m scripts.audio.import_audio --dir out/audio"
fi

log "③ mp3 → /srv/fojin/audio/（nginx 静态直出）"
rsync -av $DRY --include='*/' --include='*.mp3' --exclude='*' --prune-empty-dirs \
  -e "ssh $SSH_OPTS" "$LOCAL_OUT" "$VPS:$STATIC_DIR"

if [ "$DO_NGINX" = "1" ]; then
  log "④ host nginx 配置同步 + reload"
  # ⚠️ 生产的 /etc/nginx/conf.d/fojin.conf 历史上被手工改过（那台机器上留着
  #    fojin.conf.bak-pre-cors / -realip / -bodysize 等一串备份）。仓库副本
  #    未必是它的超集，**先 diff 再覆盖**，并按同样的命名留一份回滚点。
  log "   先看差异（无输出 = 完全一致）"
  ssh $SSH_OPTS "$VPS" "sudo diff -u /etc/nginx/conf.d/fojin.conf \
    /home/admin/fojin/deploy/host-nginx/fojin.conf" || true
  [ -z "$DRY" ] && ssh $SSH_OPTS "$VPS" "
    sudo cp -a /etc/nginx/conf.d/fojin.conf \
      /etc/nginx/conf.d/fojin.conf.bak-audio-\$(date +%s) &&
    sudo cp /home/admin/fojin/deploy/host-nginx/fojin.conf /etc/nginx/conf.d/fojin.conf &&
    sudo nginx -t && sudo systemctl reload nginx"
fi

# ⚠️ 验证必须看 Content-Type，不能只看状态码：/audio/ 段没生效时
#    SPA 回退会返回 **200 + index.html**，<audio> 静默不播、无任何报错。
#    实测踩过一次（2026-08-12）。

log "验证"
FIRST_MP3=$(find "$LOCAL_OUT" -name '*.mp3' | head -1 | sed "s|^$LOCAL_OUT||")
echo "  音频:"
CT=$(curl -sI "https://fojin.app/audio/$FIRST_MP3" \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="content-type"{print $2}' | tail -1)
echo "    Content-Type: ${CT:-（无）}"
case "$CT" in
  audio/*) echo "    ✅ 真音频" ;;
  *)       echo "    ❌ 不是音频 —— /audio/ 段没生效，SPA 回退成 index.html 了。"
           echo "       补跑：./deploy/deploy-audio.sh --nginx" ;;
esac
echo "  API:"
TID=$(echo "$FIRST_MP3" | cut -d/ -f1)
curl -s "https://fojin.app/api/texts/$TID/juans/1/audio" | head -c 180 | sed 's/^/    /'
echo
log "完成。打开 https://fojin.app/texts/$TID/read?juan=1 确认顶栏出现「读诵」按钮。"
