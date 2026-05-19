"""Remove dynasty-based proxy coordinates, keep only real data.

Keeps: DILA original coords + active_in propagated coords + manual enrichment
Removes: dynasty:* proxy coords

Then re-runs active_in propagation to ensure all possible real coords are assigned.

Usage:
    python -m scripts.cleanup_dynasty_coords [--dry-run]
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Cleanup: remove dynasty proxy coords, keep real data only")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # 1. Count before
        r = await session.execute(text(
            "SELECT COUNT(*) FROM kg_entities WHERE (properties->>'latitude') IS NOT NULL"
        ))
        total_before = r.scalar()

        r = await session.execute(text(
            "SELECT COUNT(*) FROM kg_entities WHERE properties->>'geo_source' LIKE 'dynasty:%'"
        ))
        dynasty_count = r.scalar()

        r = await session.execute(text(
            "SELECT COUNT(*) FROM kg_entities WHERE properties->>'geo_source' LIKE 'active_in:%'"
        ))
        active_in_count = r.scalar()

        r = await session.execute(text("""
            SELECT COUNT(*) FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (properties->>'geo_source' IS NULL OR properties->>'geo_source' NOT LIKE 'dynasty:%')
        """))
        real_count = r.scalar()

        print(f"Before: {total_before} total with coords")
        print(f"  dynasty proxy (to remove): {dynasty_count}")
        print(f"  active_in (real, keep): {active_in_count}")
        print(f"  DILA/manual (real, keep): {real_count - active_in_count}")
        print(f"After removal: {real_count} will remain")

        # 2. Remove dynasty proxies
        if not args.dry_run:
            r = await session.execute(text(
                "SELECT id FROM kg_entities WHERE properties->>'geo_source' LIKE 'dynasty:%'"
            ))
            ids = [row[0] for row in r.fetchall()]
            for eid in ids:
                entity = await session.get(KGEntity, eid)
                if entity:
                    props = dict(entity.properties or {})
                    props.pop("latitude", None)
                    props.pop("longitude", None)
                    props.pop("year_start", None)
                    props.pop("year_end", None)
                    props.pop("geo_source", None)
                    entity.properties = props
                if ids.index(eid) % 500 == 0:
                    await session.flush()
            print(f"\nRemoved {len(ids)} dynasty proxy coords")

        # 3. Re-run active_in propagation
        print("\nRe-propagating active_in coordinates...")
        r = await session.execute(text("""
            SELECT DISTINCT ON (p.id)
                p.id, pl.name_zh,
                (pl.properties->>'latitude')::float,
                (pl.properties->>'longitude')::float
            FROM kg_entities p
            JOIN kg_relations r ON r.subject_id = p.id AND r.predicate = 'active_in'
            JOIN kg_entities pl ON pl.id = r.object_id
            WHERE p.entity_type = 'person'
              AND (p.properties->>'latitude') IS NULL
              AND (pl.properties->>'latitude') IS NOT NULL
            ORDER BY p.id, r.confidence DESC
        """))
        rows = r.fetchall()
        propagated = 0
        for row in rows:
            person_id, place_name, lat, lng = row
            if not args.dry_run:
                entity = await session.get(KGEntity, person_id)
                if not entity:
                    continue
                props = dict(entity.properties or {})
                if props.get("latitude"):
                    continue
                props["latitude"] = lat
                props["longitude"] = lng
                props["geo_source"] = f"active_in:{place_name}"
                entity.properties = props
            propagated += 1
            if propagated <= 10:
                print(f"  + {place_name} → person #{person_id}")

        if propagated > 10:
            print(f"  ... and {propagated - 10} more")
        print(f"Propagated: {propagated} new")

        if not args.dry_run:
            await session.commit()

        # 4. Final count
        if not args.dry_run:
            r = await session.execute(text(
                "SELECT COUNT(*) FROM kg_entities WHERE (properties->>'latitude') IS NOT NULL"
            ))
            print(f"\nFinal total with coords: {r.scalar()}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
