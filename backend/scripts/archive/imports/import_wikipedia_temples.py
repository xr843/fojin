"""Import Wikipedia temples with rich metadata (dynasty, year, school).

Match strategy:
1. By Wikidata Q-ID (highest priority)
2. By name_zh
3. Otherwise create new monastery entity
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

INPUT = "data/wikipedia_temples.json"


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin — Wikipedia Temples Import")
    print("=" * 60)

    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} Wikipedia records")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type.in_(["place", "monastery"]))
        )
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} existing place/monastery entities")

        by_wikidata: dict[str, KGEntity] = {}
        by_name: dict[str, list[KGEntity]] = {}
        for e in entities:
            ext = e.external_ids or {}
            if ext.get("wikidata"):
                by_wikidata[ext["wikidata"]] = e
            if e.name_zh:
                by_name.setdefault(normalize(e.name_zh), []).append(e)

        stats = {
            "matched_wikidata": 0,
            "matched_name": 0,
            "enriched_metadata": 0,
            "enriched_coords": 0,
            "created": 0,
        }

        for rec in records:
            wid = rec["wikidata_id"]
            name_zh = rec.get("name_zh", "")
            name_en = rec.get("name_en", "")
            lat, lng = rec["latitude"], rec["longitude"]
            year_founded = rec.get("year_founded")
            dynasty = rec.get("dynasty")
            school = rec.get("school")
            province = rec.get("province")
            country = rec.get("country")

            # Match by Wikidata first
            entity = by_wikidata.get(wid)
            matched_type = None
            if entity:
                matched_type = "matched_wikidata"
            elif name_zh:
                candidates = by_name.get(normalize(name_zh), [])
                if candidates:
                    entity = candidates[0]
                    matched_type = "matched_name"

            if entity:
                stats[matched_type] += 1
                # Enrich with metadata (always add rich fields)
                props = dict(entity.properties or {})
                updated = False

                if not props.get("latitude"):
                    props["latitude"] = lat
                    props["longitude"] = lng
                    props["geo_source"] = f"wikipedia:{country}"
                    stats["enriched_coords"] += 1
                    updated = True

                # Add metadata fields if missing
                for field, value in [
                    ("year_founded", year_founded),
                    ("dynasty", dynasty),
                    ("school", school),
                    ("province", province),
                    ("wikipedia_url", rec.get("wikipedia_url")),
                ]:
                    if value and not props.get(field):
                        props[field] = value
                        updated = True

                if updated:
                    stats["enriched_metadata"] += 1
                    if not args.dry_run:
                        entity.properties = props

                # Add Wikidata ID if missing
                ext_ids = dict(entity.external_ids or {})
                if wid and not ext_ids.get("wikidata"):
                    ext_ids["wikidata"] = wid
                    entity.external_ids = ext_ids
                continue

            # Create new
            if not name_zh:
                continue

            props = {
                "latitude": lat,
                "longitude": lng,
                "geo_source": f"wikipedia:{country}",
                "country": country,
            }
            if year_founded:
                props["year_founded"] = year_founded
                props["year_start"] = year_founded
            if dynasty:
                props["dynasty"] = dynasty
            if school:
                props["school"] = school
            if province:
                props["province"] = province
            props["wikipedia_url"] = rec.get("wikipedia_url")

            new_entity = KGEntity(
                entity_type="monastery",
                name_zh=name_zh,
                name_en=name_en or None,
                properties=props,
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

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
