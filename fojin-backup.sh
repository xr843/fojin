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
# 以下为 host 脚本正文(逐字):
# ─────────────────────────────────────────────────────────────────────────
# FoJin auto backup — postgres dump + configs/secrets tarball
# Local: keep 3 days | OSS pg dump: keep 60 days | OSS configs: keep 14 days
# Bucket: oss://fojin-prod-backup (dedicated, was greenthumb-ai before 2026-04-15)

set -u

BACKUP_DIR=/home/admin/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PG_FILE="fojin_pg_${TIMESTAMP}.sql.gz"
CFG_FILE="fojin_configs_${TIMESTAMP}.tar.gz"
CRON_FILE="fojin_cron_${TIMESTAMP}.txt"
BUCKET="oss://fojin-prod-backup"
GPG_RECIPIENT="C8D283D7427137C35D1D086AAE6F12A74AB34DB5"  # fojin-backup pubkey; private key held off-server (see SECURITY.md)

mkdir -p "$BACKUP_DIR"

# ── 1. PostgreSQL dump (excluding regenerable embeddings) ───────────────
cd /home/admin/fojin
docker compose exec -T postgres pg_dump -U fojin -d fojin --exclude-table=text_embeddings | gzip > "${BACKUP_DIR}/${PG_FILE}"

PG_SIZE=$(stat -c%s "${BACKUP_DIR}/${PG_FILE}" 2>/dev/null || echo 0)
if [ "$PG_SIZE" -lt 1048576 ]; then
    echo "[$(date)] ERROR: pg dump too small (${PG_SIZE} bytes), aborting"
    rm -f "${BACKUP_DIR}/${PG_FILE}"
    exit 1
fi
echo "[$(date)] Local pg backup: ${BACKUP_DIR}/${PG_FILE} (${PG_SIZE} bytes)"

if gpg --batch --yes --trust-model always -r "$GPG_RECIPIENT" -o "${BACKUP_DIR}/${PG_FILE}.gpg" --encrypt "${BACKUP_DIR}/${PG_FILE}" && /usr/local/bin/ossutil cp "${BACKUP_DIR}/${PG_FILE}.gpg" "${BUCKET}/pg/${PG_FILE}.gpg" && rm -f "${BACKUP_DIR}/${PG_FILE}.gpg"; then
    echo "[$(date)] OSS pg upload success: ${BUCKET}/pg/${PG_FILE}"
else
    echo "[$(date)] WARNING: OSS pg upload failed, local backup kept"
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
find "$BACKUP_DIR" -name 'fojin_configs_*.tar.gz' -mtime +3 -delete 2>/dev/null
find "$BACKUP_DIR" -name 'fojin_cron_*.txt' -mtime +3 -delete 2>/dev/null

# ── 5. OSS retention: pg 60d, configs 14d ──────────────────────────────
prune_oss() {
  local prefix="$1"
  local days="$2"
  local cutoff
  cutoff=$(date -d "-${days} days" +%Y%m%d)
  /usr/local/bin/ossutil ls "${BUCKET}/${prefix}/" 2>/dev/null | grep -E 'fojin_(pg|configs|cron)_' | while read -r line; do
    fname=$(echo "$line" | grep -oE 'fojin_(pg|configs|cron)_[0-9]{8}')
    if [ -n "$fname" ]; then
      fdate=$(echo "$fname" | grep -oE '[0-9]{8}')
      if [ "$fdate" -lt "$cutoff" ] 2>/dev/null; then
        obj=$(echo "$line" | grep -oE 'oss://\S+')
        [ -n "$obj" ] && /usr/local/bin/ossutil rm "$obj" -f >/dev/null 2>&1
      fi
    fi
  done
}

prune_oss pg 60
prune_oss configs 14

echo "[$(date)] Backup completed"
