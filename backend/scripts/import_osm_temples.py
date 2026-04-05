"""Import OSM Buddhist temples, matching by Wikidata ID or name."""
import argparse
import asyncio
import json
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

INPUT = "data/osm_buddhist_temples.json"


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin — OSM Buddhist Temples Import")
    print("=" * 60)

    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} OSM temples")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Load existing places/monasteries
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type.in_(["place", "monastery"]))
        )
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} existing place/monastery entities")

        # Indexes
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
            "matched_name": 0,
            "created": 0,
            "skipped_no_name": 0,
        }

        for rec in records:
            osm_id = rec["osm_id"]
            wid = rec.get("wikidata", "")
            primary = rec["name_primary"]
            name_zh = rec["name_zh"]
            name_ja = rec["name_ja"]
            name_ko = rec["name_ko"]
            name_en = rec["name_en"]
            lat, lng = rec["latitude"], rec["longitude"]

            if not primary:
                stats["skipped_no_name"] += 1
                continue

            # Match by OSM ID first
            if osm_id in by_osm:
                stats["matched_osm"] += 1
                continue

            # Match by Wikidata ID
            if wid and wid in by_wikidata:
                stats["matched_wikidata"] += 1
                continue

            # Match by name (use primary as fallback)
            search_key = normalize(name_zh or primary)
            if search_key in by_name:
                stats["matched_name"] += 1
                continue

            # Create new
            ext_ids = {"osm": osm_id}
            if wid:
                ext_ids["wikidata"] = wid

            new_entity = KGEntity(
                entity_type="monastery",
                name_zh=name_zh or primary,
                name_en=name_en or None,
                properties={
                    "latitude": lat,
                    "longitude": lng,
                    "geo_source": f"osm:{rec['country']}",
                    "country": rec["country"],
                },
                external_ids=ext_ids,
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["created"] += 1

            if stats["created"] % 1000 == 0:
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
