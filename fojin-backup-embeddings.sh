#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# FoJin 向量表（text_embeddings）月度备份 — 部署在 host:/home/admin/fojin-backup-embeddings.sh，
# admin crontab 每月 1 日 05:30（避开 03:00 主备份、04:30 DILA 同步）。本文件是仓库副本，改 host 后同步。
#
# 为什么要备：每日主备份 fojin-backup.sh 有意排除这张表（"可再生"）。2026-11-27 实测重算只要约 3 小时、
# 几美元，但表里有手工修复的结果（11 月修过 1.5 万段错标卷号、MITRA 重定位等），全量重算会把它们冲掉。
# 压缩后约 3.5GB（2026-11-27 首次：15 段、662,724 行、3.53GB、用时 80 分钟），OSS 每月不到 1 元。
#
# 做法：按 id 分段 COPY → gzip → 校验行数 → gpg 加密 → 上传 oss://fojin-prod-backup/embeddings/<日期>/，
# 每段传完即删本地（磁盘峰值约 1GB；宿主只剩约 12GB）。schema 与 manifest（每段行数、sha256）一并上传。
# 只有全部段成功且总行数与表一致，才清理 70 天前的旧备份。
#
# 恢复：见本文件末尾注释；演练脚本 fojin-restore-drill-embeddings.sh（2026-11-27 演练通过：两段 sha256 对、
# 行数与 manifest 一致、各抽 200 行文字与向量和生产逐字相同）。
# ─────────────────────────────────────────────────────────────────────────
set -uo pipefail

BUCKET="oss://fojin-prod-backup"
GPG_RECIPIENT="8699CAC05E36453C0869BF62931E4CC8792263E9"
WORK=/home/admin/backups/embeddings_tmp
STAMP=$(date +%Y%m%d)
PREFIX="${BUCKET}/embeddings/${STAMP}"
STEP=${STEP:-60000}
KEEP_DAYS=70
OSSUTIL=/usr/local/bin/ossutil

cd /home/admin/fojin || exit 1
psql_q() { docker compose exec -T postgres psql -U fojin -d fojin -At -c "$1"; }

# 磁盘保护：可用不足 3GB 不开始
avail_kb=$(df --output=avail -k /home/admin | tail -1)
if [ "$avail_kb" -lt 3145728 ]; then
  echo "[$(date)] ERROR: free disk ${avail_kb}KB < 3GB, embeddings backup skipped"
  exit 1
fi

rm -rf "$WORK" && mkdir -p "$WORK" || exit 1
read -r MIN_ID MAX_ID TOTAL <<<"$(psql_q "select min(id), max(id), count(*) from text_embeddings" | tr '|' ' ')"
echo "[$(date)] embeddings backup ${STAMP}: ids ${MIN_ID}..${MAX_ID}, ${TOTAL} rows, step ${STEP}"

upload() {  # upload LOCAL_FILE NAME：加密上传，成功后删本地明文与密文
  local f="$1" name="$2"
  gpg --batch --yes --trust-model always -r "$GPG_RECIPIENT" -o "${f}.gpg" --encrypt "$f" \
    && "$OSSUTIL" cp -f "${f}.gpg" "${PREFIX}/${name}.gpg" >/dev/null \
    && rm -f "$f" "${f}.gpg"
}

# schema（含索引定义），恢复时先建表
docker compose exec -T postgres pg_dump -U fojin -d fojin -s -t text_embeddings > "${WORK}/schema.sql" \
  && grep -q "CREATE TABLE public.text_embeddings" "${WORK}/schema.sql" \
  && upload "${WORK}/schema.sql" schema.sql \
  || { echo "[$(date)] ERROR: schema dump/upload failed"; exit 1; }

FAIL=0
SUM=0
MANIFEST="${WORK}/manifest.tsv"
printf 'part\tfrom_id\tto_id\trows\tgz_bytes\tgz_sha256\n' > "$MANIFEST"
part=0
for ((a = MIN_ID; a <= MAX_ID; a += STEP)); do
  b=$((a + STEP))
  name=$(printf 'part_%04d.copy.gz' "$part")
  f="${WORK}/${name}"
  docker compose exec -T postgres psql -U fojin -d fojin -At \
    -c "\\copy (select * from text_embeddings where id >= ${a} and id < ${b} order by id) to stdout" | gzip > "$f"
  rc=("${PIPESTATUS[@]}")
  want=$(psql_q "select count(*) from text_embeddings where id >= ${a} and id < ${b}")
  got=$(gzip -dc "$f" | wc -l)
  if [ "${rc[0]}" -ne 0 ] || [ "${rc[1]}" -ne 0 ] || [ "$got" != "$want" ]; then
    echo "[$(date)] ERROR: ${name} failed (psql=${rc[0]} gzip=${rc[1]} rows ${got}/${want})"
    FAIL=1; rm -f "$f"; part=$((part + 1)); continue
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$a" "$((b - 1))" "$got" "$(stat -c%s "$f")" "$(sha256sum "$f" | cut -d' ' -f1)" >> "$MANIFEST"
  if upload "$f" "$name"; then
    SUM=$((SUM + got))
  else
    echo "[$(date)] ERROR: ${name} upload failed"; FAIL=1; rm -f "$f" "${f}.gpg"
  fi
  part=$((part + 1))
done

# 导出期间表可能有少量写入：总数与开始时的 count 差 1% 以内都算对上
if [ "$FAIL" -ne 0 ] || [ "$SUM" -lt $((TOTAL * 99 / 100)) ]; then
  echo "[$(date)] ERROR: embeddings backup incomplete (${SUM}/${TOTAL} rows, fail=${FAIL}); old backups kept"
  upload "$MANIFEST" manifest.tsv
  exit 1
fi
upload "$MANIFEST" manifest.tsv || { echo "[$(date)] ERROR: manifest upload failed"; exit 1; }
echo "[$(date)] embeddings backup OK: ${part} parts, ${SUM}/${TOTAL} rows → ${PREFIX}/"

# 清理 70 天前的整套（目录名就是日期）
cutoff=$(date -d "-${KEEP_DAYS} days" +%Y%m%d)
"$OSSUTIL" ls -d "${BUCKET}/embeddings/" 2>/dev/null | grep -oE 'embeddings/[0-9]{8}/' | sort -u | while read -r d; do
  day=${d#embeddings/}; day=${day%/}
  if [ "$day" -lt "$cutoff" ]; then
    "$OSSUTIL" rm -r -f "${BUCKET}/${d}" >/dev/null 2>&1 && echo "[$(date)] pruned ${BUCKET}/${d}"
  fi
done
rm -rf "$WORK"

# ── 恢复（2026-11-27 演练通过，见 fojin-restore-drill-embeddings.sh）──
# 1) ossutil cp -r oss://fojin-prod-backup/embeddings/<日期>/ ./emb/  2) 逐个 gpg -d x.gpg > x
# 3) 先 psql < schema.sql（需 CREATE EXTENSION vector），再对每段：gzip -dc part_XXXX.copy.gz | psql -c "\copy text_embeddings from stdin"
# 4) 核对 manifest.tsv 的行数；HNSW 索引在 schema.sql 里，建议先删索引、导完再建（快得多）
