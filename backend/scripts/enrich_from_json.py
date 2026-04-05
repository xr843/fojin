"""
Import Wikidata coordinates from pre-fetched JSON file.

Usage:
    cd backend
    python -m scripts.enrich_from_json [--dry-run]
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

INPUT = "data/wikidata_geo.json"


def normalize_zh(s: str) -> str:
    return s.strip().replace(" ", "")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 (FoJin) — Import Wikidata Coordinates from JSON")
    print("=" * 60)

    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} records from {INPUT}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Load all entities
        result = await session.execute(select(KGEntity))
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} KG entities")

        # Build name indexes
        by_zh: dict[str, list[KGEntity]] = {}
        by_en: dict[str, list[KGEntity]] = {}

        for e in entities:
            if e.name_zh:
                by_zh.setdefault(normalize_zh(e.name_zh), []).append(e)
            if e.name_en:
                by_en.setdefault(e.name_en.lower().strip(), []).append(e)

        matched = 0
        updated = 0

        for rec in records:
            candidates = []
            if rec["name_zh"]:
                candidates = by_zh.get(normalize_zh(rec["name_zh"]), [])
            if not candidates and rec["name_en"]:
                candidates = by_en.get(rec["name_en"].lower().strip(), [])

            if not candidates:
                continue

            matched += 1
            for entity in candidates:
                props = dict(entity.properties or {})
                if props.get("latitude") and props.get("longitude"):
                    continue

                props["latitude"] = rec["latitude"]
                props["longitude"] = rec["longitude"]

                ext_ids = dict(entity.external_ids or {})
                if not ext_ids.get("wikidata"):
                    ext_ids["wikidata"] = rec["wikidata_id"]
                    entity.external_ids = ext_ids

                if not args.dry_run:
                    entity.properties = props

                updated += 1
                if updated <= 30:
                    print(f"  + {entity.name_zh} ({entity.entity_type})"
                          f" ← ({rec['latitude']:.4f}, {rec['longitude']:.4f})"
                          f" [{rec['wikidata_id']}]")

                if updated % 50 == 0:
                    await session.flush()

        if updated > 30:
            print(f"  ... and {updated - 30} more")

        # Phase 2: re-propagate active_in
        print("\nRe-propagating active_in coordinates...")
        from sqlalchemy import text
        sql = """
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
        """
        result = await session.execute(text(sql))
        propagated = 0
        for row in result.fetchall():
            person_id, place_name, lat, lng = row
            entity = await session.get(KGEntity, person_id)
            if not entity:
                continue
            props = dict(entity.properties or {})
            if props.get("latitude"):
                continue
            props["latitude"] = lat
            props["longitude"] = lng
            props["geo_source"] = f"active_in:{place_name}"
            if not args.dry_run:
                entity.properties = props
            propagated += 1
            if propagated <= 10:
                print(f"  + {entity.name_zh} ← {place_name}")

        if propagated > 10:
            print(f"  ... and {propagated - 10} more")

        if not args.dry_run:
            await session.commit()

        print(f"\nSummary: matched={matched}, updated={updated}, propagated={propagated}")
        print(f"Total new coordinates: {updated + propagated}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
