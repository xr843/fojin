#!/bin/bash
# Run Amap V3 fetch + import, then use remaining quota for regeo
cd /home/admin/fojin

echo "[$(date)] === Amap V3 city-level fetch ==="
docker compose exec -T backend python scripts/fetch_amap_temples_v3.py 2>&1

# Check if V3 fetch completed (no progress file = done)
if docker compose exec -T backend test -f data/amap_v3_progress.json; then
    echo "[$(date)] V3 fetch paused (will resume tomorrow). Skipping import."
else
    if docker compose exec -T backend test -f data/amap_temples_v3.json; then
        echo "[$(date)] V3 fetch complete! Running import..."
        docker compose exec -T backend python scripts/import_amap_temples_v3.py 2>&1
        echo "[$(date)] Import done. V3 task complete."
    fi
fi

# Use remaining daily quota for reverse geocoding (~1500 calls left)
echo "[$(date)] === Reverse geocoding (remaining quota) ==="
docker compose exec -T -w /app/scripts backend python3 backfill_address_regeo.py --limit 1500 2>&1

echo "[$(date)] All done."
