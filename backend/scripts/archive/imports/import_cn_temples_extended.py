"""Import extended Chinese temples, deduplicating against existing DB entries.

Dedup strategy:
1. Match by OSM ID (external_ids.osm)
2. Match by Wikidata ID (external_ids.wikidata)
3. Match by normalized name_zh + proximity (< 2km)
4. Create new if no match

Input: data/cn_temples_extended.json
"""
import argparse
import asyncio
import json
import math
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

INPUT = "data/cn_temples_extended.json"


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "").replace("　", "")


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin — Extended CN Buddhist Temples Import")
    print("=" * 60)

    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} temple records")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type.in_(["place", "monastery"]))
        )
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} existing place/monastery entities")

        by_osm: dict[str, KGEntity] = {}
        by_wikidata: dict[str, KGEntity] = {}
        by_name: dict[str, list[KGEntity]] = {}

        for e in entities:
            ext = e.external_ids or {}
            if ext.get("osm"):
                by_osm[ext["osm"]] = e
            if ext.get("wikidata"):
                by_wikidata[ext["wikidata"]] = e
            if e.name_zh:
                by_name.setdefault(normalize(e.name_zh), []).append(e)

        stats = {
            "matched_osm": 0,
            "matched_wikidata": 0,
            "matched_name_proximity": 0,
            "created": 0,
            "skipped_no_name": 0,
        }

        for rec in records:
            osm_id = rec["osm_id"]
            wid = rec.get("wikidata", "")
            name_zh = rec.get("name_zh") or rec.get("name_primary", "")
            name_en = rec.get("name_en", "")
            lat, lng = rec["latitude"], rec["longitude"]

            if not name_zh:
                stats["skipped_no_name"] += 1
                continue

            if osm_id in by_osm:
                stats["matched_osm"] += 1
                continue

            if wid and wid in by_wikidata:
                stats["matched_wikidata"] += 1
                continue

            # Name + proximity dedup
            search_key = normalize(name_zh)
            if search_key in by_name:
                matched = False
                for existing in by_name[search_key]:
                    props = existing.properties or {}
                    e_lat = props.get("latitude")
                    e_lng = props.get("longitude")
                    if e_lat is not None and e_lng is not None:
                        dist = haversine(lat, lng, float(e_lat), float(e_lng))
                        if dist < 2.0:
                            matched = True
                            break
                    else:
                        # Same name, no coords — treat as match
                        matched = True
                        break
                if matched:
                    stats["matched_name_proximity"] += 1
                    continue

            ext_ids = {"osm": osm_id}
            if wid:
                ext_ids["wikidata"] = wid

            new_entity = KGEntity(
                entity_type="monastery",
                name_zh=name_zh,
                name_en=name_en or None,
                properties={
                    "latitude": lat,
                    "longitude": lng,
                    "geo_source": f"osm_ext:{rec.get('source', 'unknown')}",
                    "country": "CN",
                },
                external_ids=ext_ids,
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["created"] += 1

            if stats["created"] % 500 == 0:
                if not args.dry_run:
                    await session.flush()
                print(f"  ... created {stats['created']}")

        if not args.dry_run:
            await session.commit()

        print("\n" + "=" * 60)
        print("Results:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print("=" * 60)
        print(f"{'Dry run' if args.dry_run else 'Committed'}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
