"""Import East Asian Buddhist temples from Wikidata into KG.

Strategy: match by wikidata_id → match by name_zh → create new entity.

Usage:
    python -m scripts.import_east_asian_temples [--dry-run]
"""
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

INPUT = "data/east_asian_temples.json"


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin — East Asian Buddhist Temples Import")
    print("=" * 60)

    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} records from {INPUT}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Load existing entities
        result = await session.execute(
            select(KGEntity).where(
                KGEntity.entity_type.in_(["place", "monastery"])
            )
        )
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} existing place/monastery entities")

        # Build indexes
        by_wikidata: dict[str, KGEntity] = {}
        by_name_zh: dict[str, list[KGEntity]] = {}
        by_name_en: dict[str, list[KGEntity]] = {}

        for e in entities:
            ext = e.external_ids or {}
            wid = ext.get("wikidata")
            if wid:
                by_wikidata[wid] = e
            if e.name_zh:
                by_name_zh.setdefault(normalize(e.name_zh), []).append(e)
            if e.name_en:
                by_name_en.setdefault(e.name_en.lower().strip(), []).append(e)

        stats = {
            "matched_wikidata": 0,
            "matched_name": 0,
            "enriched": 0,
            "created": 0,
            "skipped": 0,
        }

        for rec in records:
            wid = rec["wikidata_id"]
            name_zh = rec.get("name_zh", "") or rec.get("name_ja", "")
            name_en = rec.get("name_en", "")
            lat = rec["latitude"]
            lng = rec["longitude"]

            # Match by wikidata ID first
            entity = by_wikidata.get(wid)
            if entity:
                stats["matched_wikidata"] += 1
                # Update coords if missing
                props = dict(entity.properties or {})
                if not props.get("latitude"):
                    props["latitude"] = lat
                    props["longitude"] = lng
                    props["geo_source"] = f"wikidata:{rec['country']}"
                    if not args.dry_run:
                        entity.properties = props
                    stats["enriched"] += 1
                continue

            # Match by name
            candidates = []
            if name_zh:
                candidates = by_name_zh.get(normalize(name_zh), [])
            if not candidates and name_en:
                candidates = by_name_en.get(name_en.lower().strip(), [])

            if candidates:
                entity = candidates[0]
                stats["matched_name"] += 1
                props = dict(entity.properties or {})
                if not props.get("latitude"):
                    props["latitude"] = lat
                    props["longitude"] = lng
                    props["geo_source"] = f"wikidata:{rec['country']}"
                    # Add wikidata ID
                    ext_ids = dict(entity.external_ids or {})
                    if not ext_ids.get("wikidata"):
                        ext_ids["wikidata"] = wid
                        entity.external_ids = ext_ids
                    if not args.dry_run:
                        entity.properties = props
                    stats["enriched"] += 1
                continue

            # Create new entity
            if not (name_zh or name_en):
                stats["skipped"] += 1
                continue

            new_entity = KGEntity(
                entity_type="monastery",
                name_zh=name_zh or name_en,
                name_en=name_en or None,
                properties={
                    "latitude": lat,
                    "longitude": lng,
                    "geo_source": f"wikidata:{rec['country']}",
                    "country": rec["country"],
                },
                external_ids={"wikidata": wid},
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["created"] += 1

            if stats["created"] % 200 == 0:
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
