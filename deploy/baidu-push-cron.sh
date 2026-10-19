#!/bin/sh
# 百度主动推送的每日任务：admin 的 crontab 每天 08:15 调用（不带参数）。
#
#   15 8 * * * /home/admin/fojin/deploy/baidu-push-cron.sh
#
# 两步：① 在 Umami 库里重新算近 90 天各内容页的访问排名；② 按排名推送 10 条
# （每日额度 10），已推过的不重推，排名用完回到按编号顺推。
#
# 额外参数原样传给 baidu_push.py——验收时用 cron 同款最小环境空跑：
#   env -i HOME=/home/admin LOGNAME=admin SHELL=/bin/sh PATH=/usr/bin:/bin \
#     /bin/sh -c '/home/admin/fojin/deploy/baidu-push-cron.sh --dry-run'
#
# 故意用 POSIX sh、绝对路径、不依赖登录环境：cron 只给 PATH=/usr/bin:/bin。
# token 从 600 权限的文件经 stdin 传入，不进环境变量、进程表和日志。
set -u

REPO=/home/admin/fojin
LOG=/home/admin/fojin-baidu-push.log
TOKEN=/home/admin/secrets/baidu-push-token
DIR=$REPO/data/baidu-push
TAB=$(printf '\t')

cd "$REPO" || { echo "=== $(date -Is) ERROR: cannot cd $REPO" >> "$LOG"; exit 1; }

{
  echo "=== $(date -Is) $*"
  if [ ! -r "$TOKEN" ]; then
    echo "ERROR: token file $TOKEN not readable"
    exit 1
  fi
  # 排名生成失败（库不可用等）时沿用上一份，推送照常——宁可旧排名，也别空转一天额度。
  if docker exec -i fojin-postgres psql -U umami -d umami -At -F "$TAB" -v ON_ERROR_STOP=1 \
       < backend/scripts/baidu_priority.sql > "$DIR/priority.tsv.tmp"; then
    mv "$DIR/priority.tsv.tmp" "$DIR/priority.tsv"
    echo "priority: $(wc -l < "$DIR/priority.tsv") paths"
  else
    rm -f "$DIR/priority.tsv.tmp"
    echo "WARN: priority refresh failed, reusing the previous file"
  fi
  docker compose exec -T backend python scripts/baidu_push.py \
    --kind all --limit 10 --token-stdin \
    --state-file /data/baidu-push/state.json \
    --priority-file /data/baidu-push/priority.tsv "$@" < "$TOKEN"
  echo "exit=$?"
} >> "$LOG" 2>&1
