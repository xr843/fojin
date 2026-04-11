"""Backfill province/city/district for CN monasteries via Amap reverse geocoding.

Targets: entity_type='monastery', country='CN', province IS NULL, has lat/lng.
Uses Amap regeo API with WGS-84→GCJ-02 conversion.

Rate limit: 0.25s between requests. ~1600 entities ≈ 7 min.
"""
import argparse
import asyncio
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

AMAP_KEY = os.environ.get("AMAP_KEY")
if not AMAP_KEY:
    sys.exit("ERROR: AMAP_KEY environment variable is not set (check .env)")
AMAP_REGEO_URL = "https://restapi.amap.com/v3/geocode/regeo"
USER_AGENT = "FoJinBot/1.0"


def wgs84_to_gcj02(lng, lat):
    """Convert WGS-84 to GCJ-02."""
    a = 6378245.0
    ee = 0.00669342162296594323

    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lon(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def _transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def regeo(lng_wgs, lat_wgs) -> dict | None:
    lng_gcj, lat_gcj = wgs84_to_gcj02(lng_wgs, lat_wgs)
    params = urllib.parse.urlencode({
        "key": AMAP_KEY,
        "location": f"{lng_gcj:.6f},{lat_gcj:.6f}",
        "extensions": "base",
        "output": "json",
    })
    url = f"{AMAP_REGEO_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "1":
        return None
    comp = data.get("regeocode", {}).get("addressComponent", {})
    province = comp.get("province", "")
    city = comp.get("city", "")
    district = comp.get("district", "")
    # Amap returns [] for empty fields in municipalities
    if isinstance(province, list):
        province = ""
    if isinstance(city, list):
        city = ""
    if isinstance(district, list):
        district = ""
    if not province:
        return None
    return {"province": province, "city": city or province, "district": district}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin — Backfill Address via Amap Reverse Geocoding")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        result = await session.execute(text("""
            SELECT id, name_zh,
                   (properties->>'latitude')::float AS lat,
                   (properties->>'longitude')::float AS lng
            FROM kg_entities
            WHERE entity_type = 'monastery'
              AND (properties->>'country' = 'CN' OR properties->>'country' = '中国'
                   OR properties->>'geo_source' LIKE 'osm:CN%' OR properties->>'geo_source' LIKE 'osm:中国%'
                   OR properties->>'geo_source' LIKE 'osm_ext%')
              AND COALESCE(properties->>'geo_source', '') <> 'bdrc'
              AND (properties->>'province' IS NULL OR properties->>'province' = '')
              AND properties->>'latitude' IS NOT NULL
            LIMIT :limit
        """), {"limit": args.limit})
        rows = result.fetchall()
        print(f"Found {len(rows)} monasteries to backfill")

        stats = {"updated": 0, "failed": 0, "skipped": 0}

        for i, (eid, name, lat, lng) in enumerate(rows):
            try:
                addr = regeo(lng, lat)
                time.sleep(0.25)
            except Exception as e:
                print(f"  ERR {eid} {name}: {e}")
                stats["failed"] += 1
                time.sleep(1)
                continue

            if not addr:
                stats["skipped"] += 1
                continue

            if not args.dry_run:
                props_patch = json.dumps(addr)
                await session.execute(text("""
                    UPDATE kg_entities
                    SET properties = (properties::jsonb || cast(:patch as jsonb))::json
                    WHERE id = :id
                """), {"id": eid, "patch": props_patch})

            stats["updated"] += 1

            if (i + 1) % 200 == 0:
                if not args.dry_run:
                    await session.commit()
                print(f"  [{i+1}/{len(rows)}] updated: {stats['updated']}, failed: {stats['failed']}")

        if not args.dry_run:
            await session.commit()

        print(f"\n{'='*60}")
        print(f"Results: {stats}")
        print(f"{'Dry run' if args.dry_run else 'Committed'}")
        print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
