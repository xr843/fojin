#!/usr/bin/env bash
#
# fojin PostgreSQL 备份脚本 —— 幂等、可轮转、可异地。
#
#   用法:
#     ./backup_db.sh            # 跑一次备份(globals + fojin 库)+ 轮转
#     ./backup_db.sh --verify   # 校验最新一份 dump 可被 pg_restore 读取(不真恢复)
#
# 为什么需要它:
#   90 万跨语对齐 + 4.4 万人物 + 本地全文都是人月级、不可再生的资产,
#   此前生产库没有任何自动备份。一次误 drop / 磁盘损坏 / dockerd OOM
#   就是数月蒸发且不可逆。这是单点最高 ROI 的止血。
#
# 设计要点:
#   - 两段式 dump:`pg_dumpall --globals-only`(角色/权限)+ `pg_dump -Fc`
#     (fojin 库,custom 格式,自带压缩、支持并行/选择性恢复)。两者合起来
#     才能在一台空机器上完整重建。
#   - CORE vs FULL:fojin 库 16GB,其中 text_embeddings(pgvector)~10GB 且可再生。
#     默认 CORE 备份用 --exclude-table-data 跳过它的数据(保留表结构),把 dump
#     压到 ~2GB、几分钟跑完、对生产盘安全;FULL_DUMP=1 才含全部(慎用,见上)。
#   - 先写 .tmp 再 mv:pg_dump 中途失败(pipefail 捕获)不会留下半截"成功"文件。
#   - 本地按日轮转(默认留 3 份,受生产盘空闲约束)—— 长期保留靠异地推送。
#   - 异地推送是可选 env 开关(BACKUP_RSYNC_DEST 走 tailscale rsync /
#     BACKUP_OSS_DEST 走 ossutil),脚本不硬编码任何密钥/目的地。
#   - 失败即非零退出(set -e),交给 cron 的邮件/日志暴露,不静默吞错。
#
# 恢复速查(灾难时):
#   gunzip -c globals-YYYYMMDD.sql.gz | docker exec -i <新pg> psql -U postgres
#   docker exec -i <新pg> pg_restore -U fojin -d fojin --clean --if-exists < fojin-YYYYMMDD.dump
#   # CORE dump 恢复后 text_embeddings 为空 → 跑嵌入管线重嵌后语义搜索才恢复;
#   # 其余所有数据(text_contents / mitra_alignments / alignment_pairs / 词典 /
#   # KG / 人物 / 用户 …)都已完整恢复。
#
# 建议 cron(VPS,每日 03:10,避开 0:30 高德 / 3:30 DILA 同步):
#   10 3 * * *  /home/admin/fojin/backup_db.sh >> /home/admin/fojin/logs/backup.log 2>&1
#
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/home/admin/fojin/backups}"
PG_CONTAINER="${PG_CONTAINER:-fojin-postgres}"
PG_USER="${PG_USER:-fojin}"
PG_DB="${PG_DB:-fojin}"
KEEP_DAILY="${KEEP_DAILY:-3}"   # 份数 × ~2GB core dump 要塞进生产盘空闲,别贪多;长期靠异地
# text_embeddings 是 pgvector 嵌入表,约 10GB / 占 fojin 库 62%,且**可再生**
# (从 text_contents 经 BGE-M3 嵌入管线重算)。默认 "core" 备份只跳它的**数据**
# (--exclude-table-data 保留表定义,恢复后是空表,可直接重嵌),把 dump 压到
# ~2GB、几分钟跑完、对生产盘安全。FULL_DUMP=1 则含全部表(仅在盘有富余 + 低峰跑)。
EXCLUDE_TABLE_DATA="${EXCLUDE_TABLE_DATA:-public.text_embeddings}"
FULL_DUMP="${FULL_DUMP:-0}"
# 可选异地:二选一(或都不填 = 仅本地)
BACKUP_RSYNC_DEST="${BACKUP_RSYNC_DEST:-}"   # 例: la-vps:/home/user/fojin-backups
BACKUP_OSS_DEST="${BACKUP_OSS_DEST:-}"       # 例: oss://my-bucket/fojin-backups

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { log "!!! $*"; exit 1; }

latest_dump() {
  ls -1t "$BACKUP_DIR"/fojin-*.dump 2>/dev/null | head -1
}

# --- 校验模式:只检查最新 dump 是否可读,不恢复 ---
if [ "${1:-}" = "--verify" ]; then
  d="$(latest_dump)" || true
  [ -n "${d:-}" ] || die "没有可校验的 dump(目录: $BACKUP_DIR)"
  log "校验 $d ..."
  if docker exec -i "$PG_CONTAINER" pg_restore --list < "$d" > /dev/null; then
    log "OK: $d 可被 pg_restore 读取($(du -h "$d" | cut -f1))"
  else
    die "$d 损坏:pg_restore --list 失败"
  fi
  exit 0
fi

# --- 备份模式 ---
command -v docker >/dev/null || die "docker 不在 PATH"
docker inspect "$PG_CONTAINER" >/dev/null 2>&1 || die "容器 $PG_CONTAINER 不存在"

mkdir -p "$BACKUP_DIR"

# 磁盘预检:把盘写满会拖垮 postgres/ES 等共盘服务(fojin 有磁盘防御史),
# 宁可提前安全退出也不写到 0 字节。默认要求至少 4GB 可用(core dump ~2GB + 余量),
# 可用 MIN_FREE_MB 覆盖;FULL_DUMP 时务必自行确保 ≥20GB 空闲。
MIN_FREE_MB="${MIN_FREE_MB:-4096}"
free_mb="$(df -Pm "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
if [ -n "${free_mb:-}" ] && [ "$free_mb" -lt "$MIN_FREE_MB" ]; then
  die "可用空间不足:$BACKUP_DIR 仅剩 ${free_mb}MB < 阈值 ${MIN_FREE_MB}MB,本次跳过(防止写满盘)"
fi

stamp="$(date '+%Y%m%d-%H%M%S')"
globals="$BACKUP_DIR/globals-$stamp.sql.gz"
dump="$BACKUP_DIR/fojin-$stamp.dump"
# 中途失败时清掉半截 .tmp,避免在磁盘防御场景下积累垃圾
trap 'rm -f "$globals.tmp" "$dump.tmp"' EXIT

log "=== fojin 备份开始 (容器=$PG_CONTAINER 库=$PG_DB) ==="

# 1) 角色/权限(globals)
log "导出 globals -> $globals"
docker exec "$PG_CONTAINER" pg_dumpall -U "$PG_USER" --globals-only \
  | gzip > "$globals.tmp"
mv "$globals.tmp" "$globals"

# 2) fojin 库(custom 格式,自带压缩)
dump_args=(-U "$PG_USER" -Fc)
if [ "$FULL_DUMP" = "1" ]; then
  log "FULL 备份(含全部表数据)-> $dump"
else
  IFS=',' read -ra _ex <<< "$EXCLUDE_TABLE_DATA"
  for tbl in "${_ex[@]}"; do
    [ -n "$tbl" ] && dump_args+=(--exclude-table-data="$tbl")
  done
  log "CORE 备份(排除可再生数据: $EXCLUDE_TABLE_DATA;FULL_DUMP=1 可全量)-> $dump"
fi
docker exec "$PG_CONTAINER" pg_dump "${dump_args[@]}" "$PG_DB" > "$dump.tmp"
mv "$dump.tmp" "$dump"

# 3) 即时完整性检查(读得通才算成功)
docker exec -i "$PG_CONTAINER" pg_restore --list < "$dump" > /dev/null \
  || die "刚生成的 $dump 无法被 pg_restore 读取,备份视为失败"
log "完整性检查通过:fojin=$(du -h "$dump" | cut -f1) globals=$(du -h "$globals" | cut -f1)"

# 4) 本地轮转(按 mtime 删超过 KEEP_DAILY 天的)
find "$BACKUP_DIR" -maxdepth 1 -name 'fojin-*.dump'     -mtime +"$KEEP_DAILY" -print -delete
find "$BACKUP_DIR" -maxdepth 1 -name 'globals-*.sql.gz' -mtime +"$KEEP_DAILY" -print -delete

# 5) 可选异地推送
if [ -n "$BACKUP_RSYNC_DEST" ]; then
  log "异地 rsync -> $BACKUP_RSYNC_DEST"
  rsync -az "$dump" "$globals" "$BACKUP_RSYNC_DEST/" || log "!!! rsync 异地失败(本地备份仍在)"
fi
if [ -n "$BACKUP_OSS_DEST" ]; then
  if command -v ossutil >/dev/null; then
    log "异地 OSS -> $BACKUP_OSS_DEST"
    ossutil cp "$dump"    "$BACKUP_OSS_DEST/" -f >/dev/null || log "!!! OSS 推送 dump 失败"
    ossutil cp "$globals" "$BACKUP_OSS_DEST/" -f >/dev/null || log "!!! OSS 推送 globals 失败"
  else
    log "!!! 配置了 BACKUP_OSS_DEST 但 ossutil 不在 PATH,跳过异地"
  fi
fi

log "=== 备份完成 ==="
