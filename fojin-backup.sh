#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────
# PROVENANCE / 来源说明(本副本为版本控制 bus-factor,非从 repo 运行):
#   这是生产 VPS(sg-vps)上 *实际运行* 的备份脚本的忠实副本。
#   - 部署位置:host:/home/admin/fojin-backup.sh(在 repo 目录之外,手动管理)
#   - 调度:admin crontab,每日 03:00
#   - OSS 凭据:走 host 的 ~/.ossutilconfig,**不在本脚本/repo 内**
#   - 提交动机:2026-06-13 审计的 bus-factor follow-up(运维脚本入 repo);
#     之前误以为"零备份"并加了重复脚本 backup_db.sh,经核实既有此脚本完备
#     (CORE dump 排除可再生 text_embeddings + OSS 60 天异地 + configs/secrets),
#     遂以本忠实副本取代之。修改生产脚本逻辑须先改 host 再同步此副本。
# 最近同步:2026-10-15(加 pipefail + dump 完整性校验 + 上传成功才 prune;此前副本缺 umami 段)。
# 以下为 host 脚本正文(逐字):
# ─────────────────────────────────────────────────────────────────────────
# FoJin auto backup — postgres dump + configs/secrets tarball
# Local: keep 3 days | OSS pg+umami dumps: keep 60 days | OSS configs: keep 14 days
# Bucket: oss://fojin-prod-backup (dedicated, was greenthumb-ai before 2026-04-15)

# pipefail: without it `pg_dump | gzip` reports gzip's status, so a pg_dump that
# dies halfway (OOM kill, statement timeout, disk full) leaves a truncated file
# that used to pass the size check and get uploaded as a "good" backup.
# No `-e`: every step below checks its own result and decides warn vs abort.
set -uo pipefail

BACKUP_DIR=/home/admin/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PG_FILE="fojin_pg_${TIMESTAMP}.sql.gz"
UMAMI_FILE="fojin_umami_${TIMESTAMP}.sql.gz"
CFG_FILE="fojin_configs_${TIMESTAMP}.tar.gz"
CRON_FILE="fojin_cron_${TIMESTAMP}.txt"
BUCKET="oss://fojin-prod-backup"
# fojin-backup pubkey. NOTE (2026-08-05): the SECRET key is present on this
# host under ~/.gnupg and has no passphrase — the earlier claim that it was
# "held off-server" was false. An off-server copy now exists on the operator's
# workstation; losing this host must not mean losing the ability to decrypt.
GPG_RECIPIENT="8699CAC05E36453C0869BF62931E4CC8792263E9"

mkdir -p "$BACKUP_DIR"

# verify_dump FILE DUMP_RC GZIP_RC MIN_BYTES LABEL
# A dump counts only if pg_dump and gzip both exited 0, the file is big enough,
# the gzip stream decompresses cleanly, and pg_dump's own end-of-dump marker is
# present (pg_dump writes it last, so a truncated dump never has it).
verify_dump() {
  local file="$1" dump_rc="$2" gzip_rc="$3" min="$4" label="$5" size
  if [ "$dump_rc" -ne 0 ] || [ "$gzip_rc" -ne 0 ]; then
    echo "[$(date)] ERROR: ${label} dump pipeline failed (pg_dump=${dump_rc} gzip=${gzip_rc})"
    return 1
  fi
  size=$(stat -c%s "$file" 2>/dev/null || echo 0)
  if [ "$size" -lt "$min" ]; then
    echo "[$(date)] ERROR: ${label} dump too small (${size} bytes)"
    return 1
  fi
  if ! gzip -dc "$file" | tail -c 2048 | grep -q 'PostgreSQL database dump complete'; then
    echo "[$(date)] ERROR: ${label} dump is corrupt or truncated (no end-of-dump marker)"
    return 1
  fi
  return 0
}

# OSS pruning below only runs for a prefix whose upload succeeded today, so a
# broken upload path (expired credentials, bucket policy change) can never
# quietly age the whole off-site history out of existence.
PG_UPLOADED=0
UMAMI_UPLOADED=0
CFG_UPLOADED=0

# ── 1. PostgreSQL dump (excluding regenerable embeddings) ───────────────
cd /home/admin/fojin
docker compose exec -T postgres pg_dump -U fojin -d fojin --exclude-table=text_embeddings | gzip > "${BACKUP_DIR}/${PG_FILE}"
PG_RC=("${PIPESTATUS[@]}")

if ! verify_dump "${BACKUP_DIR}/${PG_FILE}" "${PG_RC[0]}" "${PG_RC[1]}" 1048576 pg; then
    echo "[$(date)] ERROR: pg backup rejected, aborting (nothing uploaded, nothing pruned)"
    rm -f "${BACKUP_DIR}/${PG_FILE}"
    exit 1
fi
PG_SIZE=$(stat -c%s "${BACKUP_DIR}/${PG_FILE}")
echo "[$(date)] Local pg backup: ${BACKUP_DIR}/${PG_FILE} (${PG_SIZE} bytes)"

if gpg --batch --yes --trust-model always -r "$GPG_RECIPIENT" -o "${BACKUP_DIR}/${PG_FILE}.gpg" --encrypt "${BACKUP_DIR}/${PG_FILE}" && /usr/local/bin/ossutil cp "${BACKUP_DIR}/${PG_FILE}.gpg" "${BUCKET}/pg/${PG_FILE}.gpg" && rm -f "${BACKUP_DIR}/${PG_FILE}.gpg"; then
    echo "[$(date)] OSS pg upload success: ${BUCKET}/pg/${PG_FILE}"
    PG_UPLOADED=1
else
    echo "[$(date)] WARNING: OSS pg upload failed, local backup kept"
fi

# ── 1b. Umami analytics DB dump ─────────────────────────────────────────
# Umami lives in a SEPARATE database on the same postgres instance, so the
# `-d fojin` dump above does not touch it. Its traffic history is
# irreplaceable: Cloudflare's numbers are ~99.7% bot noise, which makes
# Umami the only trustworthy record of real usage.
# Unlike the pg dump, a failure here only warns — analytics must never
# abort the run and cost us the core backup.
docker compose exec -T postgres pg_dump -U fojin -d umami | gzip > "${BACKUP_DIR}/${UMAMI_FILE}"
UMAMI_RC=("${PIPESTATUS[@]}")

if ! verify_dump "${BACKUP_DIR}/${UMAMI_FILE}" "${UMAMI_RC[0]}" "${UMAMI_RC[1]}" 102400 umami; then
    echo "[$(date)] WARNING: umami backup rejected, skipping upload"
    rm -f "${BACKUP_DIR}/${UMAMI_FILE}"
else
    UMAMI_SIZE=$(stat -c%s "${BACKUP_DIR}/${UMAMI_FILE}")
    echo "[$(date)] Local umami backup: ${BACKUP_DIR}/${UMAMI_FILE} (${UMAMI_SIZE} bytes)"
    if gpg --batch --yes --trust-model always -r "$GPG_RECIPIENT" -o "${BACKUP_DIR}/${UMAMI_FILE}.gpg" --encrypt "${BACKUP_DIR}/${UMAMI_FILE}" && /usr/local/bin/ossutil cp "${BACKUP_DIR}/${UMAMI_FILE}.gpg" "${BUCKET}/umami/${UMAMI_FILE}.gpg" && rm -f "${BACKUP_DIR}/${UMAMI_FILE}.gpg"; then
        echo "[$(date)] OSS umami upload success: ${BUCKET}/umami/${UMAMI_FILE}"
        UMAMI_UPLOADED=1
    else
        echo "[$(date)] WARNING: OSS umami upload failed, local backup kept"
    fi
fi

# ── 2. Configs + secrets + scripts tarball ──────────────────────────────
# These are the "non-data" things needed to rebuild a working FoJin VPS
# from scratch. Without them, restoring the pg dump still leaves you
# stuck reconstructing every script and re-acquiring every API key.
TARBALL_LIST=$(mktemp)
{
  # Shell scripts in /home/admin
  ls /home/admin/*.sh 2>/dev/null
  # FoJin secrets (the most irreplaceable item — LLM keys, JWT, db creds)
  [ -f /home/admin/fojin/backend/.env ] && echo /home/admin/fojin/backend/.env
  [ -f /home/admin/fojin/.env ] && echo /home/admin/fojin/.env
  # Docker daemon config + drop-ins
  [ -f /etc/docker/daemon.json ] && echo /etc/docker/daemon.json
  [ -d /etc/systemd/system/docker.service.d ] && echo /etc/systemd/system/docker.service.d
  # User systemd unit overrides (openclaw, hermes, etc.)
  [ -d /home/admin/.config/systemd/user ] && echo /home/admin/.config/systemd/user
  # OpenClaw / Hermes config
  [ -f /home/admin/.openclaw/openclaw.json ] && echo /home/admin/.openclaw/openclaw.json
  [ -f /home/admin/.hermes/hermes.json ] && echo /home/admin/.hermes/hermes.json
} > "$TARBALL_LIST"

# tar with sudo so we can read root-owned /etc files
sudo -n tar czf "${BACKUP_DIR}/${CFG_FILE}" -T "$TARBALL_LIST" 2>/dev/null
rm -f "$TARBALL_LIST"

CFG_SIZE=$(stat -c%s "${BACKUP_DIR}/${CFG_FILE}" 2>/dev/null || echo 0)
if [ "$CFG_SIZE" -lt 1024 ]; then
    echo "[$(date)] WARNING: configs tarball too small (${CFG_SIZE} bytes)"
else
    echo "[$(date)] Local configs backup: ${BACKUP_DIR}/${CFG_FILE} (${CFG_SIZE} bytes)"
    if gpg --batch --yes --trust-model always -r "$GPG_RECIPIENT" -o "${BACKUP_DIR}/${CFG_FILE}.gpg" --encrypt "${BACKUP_DIR}/${CFG_FILE}" && /usr/local/bin/ossutil cp "${BACKUP_DIR}/${CFG_FILE}.gpg" "${BUCKET}/configs/${CFG_FILE}.gpg" && rm -f "${BACKUP_DIR}/${CFG_FILE}.gpg"; then
        echo "[$(date)] OSS configs upload success: ${BUCKET}/configs/${CFG_FILE}"
        CFG_UPLOADED=1
    else
        echo "[$(date)] WARNING: OSS configs upload failed"
    fi
fi

# ── 3. Crontab dump (admin + root) ──────────────────────────────────────
{
  echo "=== admin crontab ($(date)) ==="
  crontab -l 2>&1
  echo
  echo "=== root crontab ($(date)) ==="
  sudo -n crontab -l 2>&1
} > "${BACKUP_DIR}/${CRON_FILE}"

if [ -s "${BACKUP_DIR}/${CRON_FILE}" ]; then
    /usr/local/bin/ossutil cp "${BACKUP_DIR}/${CRON_FILE}" "${BUCKET}/configs/${CRON_FILE}" >/dev/null 2>&1 \
        && echo "[$(date)] OSS cron upload success: ${BUCKET}/configs/${CRON_FILE}"
fi

# ── 4. Local retention: keep 3 days ─────────────────────────────────────
find "$BACKUP_DIR" -name 'fojin_pg_*.sql.gz' -mtime +3 -delete 2>/dev/null
find "$BACKUP_DIR" -name 'fojin_umami_*.sql.gz' -mtime +3 -delete 2>/dev/null
find "$BACKUP_DIR" -name 'fojin_configs_*.tar.gz' -mtime +3 -delete 2>/dev/null
find "$BACKUP_DIR" -name 'fojin_cron_*.txt' -mtime +3 -delete 2>/dev/null

# ── 5. OSS retention: pg 60d, umami 60d, configs 14d ───────────────────
prune_oss() {
  local prefix="$1"
  local days="$2"
  local cutoff
  cutoff=$(date -d "-${days} days" +%Y%m%d)
  /usr/local/bin/ossutil ls "${BUCKET}/${prefix}/" 2>/dev/null | grep -E 'fojin_(pg|umami|configs|cron)_' | while read -r line; do
    fname=$(echo "$line" | grep -oE 'fojin_(pg|umami|configs|cron)_[0-9]{8}')
    if [ -n "$fname" ]; then
      fdate=$(echo "$fname" | grep -oE '[0-9]{8}')
      if [ "$fdate" -lt "$cutoff" ] 2>/dev/null; then
        obj=$(echo "$line" | grep -oE 'oss://\S+')
        [ -n "$obj" ] && /usr/local/bin/ossutil rm "$obj" -f >/dev/null 2>&1
      fi
    fi
  done
}

prune_if_uploaded() {
  local uploaded="$1" prefix="$2" days="$3"
  if [ "$uploaded" -eq 1 ]; then
    prune_oss "$prefix" "$days"
  else
    echo "[$(date)] WARNING: skipping OSS prune of ${prefix}/ — today's upload did not succeed"
  fi
}

prune_if_uploaded "$PG_UPLOADED" pg 60
prune_if_uploaded "$UMAMI_UPLOADED" umami 60
prune_if_uploaded "$CFG_UPLOADED" configs 14

if [ "$PG_UPLOADED" -eq 1 ]; then
    echo "[$(date)] Backup completed"
else
    echo "[$(date)] Backup completed WITH ERRORS — pg dump is local only, not off-site"
    exit 1
fi
