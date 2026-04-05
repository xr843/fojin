"""Propagate translation_site coordinates to translator persons.

For each translated_at(text, place) relation:
  Find the translator(s) via translated(person, text) relation.
  If person has no coords AND place has coords → assign place coords to person.
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

    print("Propagating translation_site coords to translators...")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Find translator-place chains via translated + translated_at
        result = await session.execute(text("""
            SELECT DISTINCT ON (tr.subject_id)
                tr.subject_id as translator_id,
                p.name_zh as place_name,
                (p.properties->>'latitude')::float as lat,
                (p.properties->>'longitude')::float as lng
            FROM kg_relations tr
            JOIN kg_relations ta ON ta.subject_id = tr.object_id
            JOIN kg_entities p ON p.id = ta.object_id
            JOIN kg_entities per ON per.id = tr.subject_id
            WHERE tr.predicate = 'translated'
              AND ta.predicate = 'translated_at'
              AND per.entity_type = 'person'
              AND (per.properties->>'latitude') IS NULL
              AND (p.properties->>'latitude') IS NOT NULL
            ORDER BY tr.subject_id, tr.confidence DESC NULLS LAST
        """))
        rows = result.fetchall()
        print(f"Found {len(rows)} translators to update")

        updated = 0
        for row in rows:
            pid, place_name, lat, lng = row
            if not args.dry_run:
                entity = await session.get(KGEntity, pid)
                if not entity:
                    continue
                props = dict(entity.properties or {})
                if props.get("latitude"):
                    continue
                props["latitude"] = lat
                props["longitude"] = lng
                props["geo_source"] = f"translation_site:{place_name}"
                entity.properties = props
            updated += 1
            if updated <= 20:
                print(f"  + translator #{pid} → {place_name} ({lat:.4f}, {lng:.4f})")

        if updated > 20:
            print(f"  ... and {updated - 20} more")

        if not args.dry_run:
            await session.commit()

        print(f"\nUpdated: {updated} translators")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
