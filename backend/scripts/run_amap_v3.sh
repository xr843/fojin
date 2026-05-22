#!/bin/bash
# Cron entry: V3 fetch is disabled (Amap free quota too small — V3 search
# endpoint allows ~100 calls/day, which is exhausted on resume before the
# first new city completes). 16-day no-progress confirmed 2026-05-23.
# Existing data: 15863 POIs in data/amap_temples_v3.json (165/396 cities,
# ~42% coverage), pending typecode/keyword filter pass before import —
# see project memory `project_fojin_amap_v3.md` for revival path.
#
# Reverse-geocoding backfill still has work (9k+ monasteries with empty
# addresses as of 2026-05-23) and uses a separate quota pool, so we keep
# running that part on the same cron slot.
cd /home/admin/fojin

echo "[$(date)] === Reverse geocoding (Amap regeo) ==="
docker compose exec -T -w /app/scripts backend python3 backfill_address_regeo.py --limit 1500 2>&1

echo "[$(date)] All done."
