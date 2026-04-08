"""Backfill coordinates for person entities by matching monastery names in descriptions.

Strategy:
1. Extract temple names from person descriptions (regex for XX寺/XX院/XX庵 etc.)
2. Match against existing monastery entities with coordinates
3. Assign the monastery's coordinates to the person with geo_source='desc_match:寺名'

Also propagates coordinates via teacher_of relations as fallback.
"""
import asyncio
import json
import os
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

# Patterns to extract monastery names from descriptions
# Match 2-6 chars before 寺/院/庵/堂/庙/禅寺/精舍/丛林
TEMPLE_PATTERN = re.compile(
    r'(?:於|于|在|居|住|主|入|依|投|參|至|往|赴|詣|游|遊|到|住持|開山|創建|出家|披剃|祝髮|受具|掛錫|結夏|安居)'
    r'([\u4e00-\u9fff]{2,8}(?:寺|院|庵|庙|廟|堂|精舍|叢林|丛林|蘭若|兰若|道場|道场|禪林|禅林))'
)

# Simpler fallback: any XX寺 pattern (3-10 chars ending in temple suffix)
TEMPLE_SIMPLE = re.compile(
    r'([\u4e00-\u9fff]{2,8}(?:禪寺|禅寺|佛寺|古寺|大寺|名寺|律寺|教寺|講寺|讲寺))'
    r'|'
    r'([\u4e00-\u9fff]{2,6}(?:寺|院|庵))'
)


async def main():
    print("=" * 60)
    print("FoJin — Backfill Person Coordinates from Descriptions")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Step 1: Build monastery name -> coords lookup
        print("Building monastery coordinate index...")
        result = await session.execute(text("""
            SELECT name_zh,
                   (properties->>'latitude')::float AS lat,
                   (properties->>'longitude')::float AS lng
            FROM kg_entities
            WHERE entity_type = 'monastery'
              AND properties->>'latitude' IS NOT NULL
              AND name_zh IS NOT NULL AND name_zh != ''
        """))
        monastery_coords = {}
        for name, lat, lng in result.fetchall():
            # Use first occurrence (don't overwrite)
            if name not in monastery_coords:
                monastery_coords[name] = (lat, lng)
        print(f"  Indexed {len(monastery_coords)} monasteries with coords")

        # Step 2: Get persons without coordinates but with descriptions
        result = await session.execute(text("""
            SELECT id, name_zh, description
            FROM kg_entities
            WHERE entity_type = 'person'
              AND (properties->>'latitude') IS NULL
              AND description IS NOT NULL AND description != ''
        """))
        persons = result.fetchall()
        print(f"  Found {len(persons)} persons without coords (with description)")

        # Step 3: Match
        stats = {"matched": 0, "no_match": 0}
        updates = []

        for pid, pname, desc in persons:
            # Try contextual pattern first
            matches = TEMPLE_PATTERN.findall(desc)
            if not matches:
                # Fallback to simple pattern
                m2 = TEMPLE_SIMPLE.findall(desc)
                matches = [g1 or g2 for g1, g2 in m2 if g1 or g2]

            # Try to find coordinates for any matched temple
            found = False
            for temple_name in matches:
                if temple_name in monastery_coords:
                    lat, lng = monastery_coords[temple_name]
                    updates.append((pid, lat, lng, f"desc_match:{temple_name}"))
                    found = True
                    break

            if found:
                stats["matched"] += 1
            else:
                stats["no_match"] += 1

        print(f"\n  Description matching: {stats['matched']} matched, {stats['no_match']} no match")

        # Step 4: Teacher propagation for remaining
        print("\n  Propagating via teacher_of relations...")
        result = await session.execute(text("""
            SELECT DISTINCT ON (p.id) p.id,
                   (t.properties->>'latitude')::float AS lat,
                   (t.properties->>'longitude')::float AS lng,
                   t.name_zh AS teacher_name
            FROM kg_entities p
            JOIN kg_relations r ON (r.subject_id = p.id OR r.object_id = p.id) AND r.predicate = 'teacher_of'
            JOIN kg_entities t ON t.id = CASE WHEN r.subject_id = p.id THEN r.object_id ELSE r.subject_id END
            WHERE p.entity_type = 'person'
              AND (p.properties->>'latitude') IS NULL
              AND (t.properties->>'latitude') IS NOT NULL
        """))
        teacher_rows = result.fetchall()

        # Exclude those already matched by description
        matched_ids = {u[0] for u in updates}
        teacher_updates = [
            (pid, lat, lng, f"teacher_propagation:{tname}")
            for pid, lat, lng, tname in teacher_rows
            if pid not in matched_ids
        ]
        print(f"  Teacher propagation: {len(teacher_updates)} additional matches")

        # Step 5: Apply all updates
        all_updates = updates + teacher_updates
        print(f"\n  Total updates to apply: {len(all_updates)}")

        for i, (pid, lat, lng, geo_src) in enumerate(all_updates):
            patch = json.dumps({"latitude": str(lat), "longitude": str(lng), "geo_source": geo_src})
            await session.execute(text("""
                UPDATE kg_entities
                SET properties = (properties::jsonb || cast(:patch as jsonb))::json
                WHERE id = :id
            """), {"id": pid, "patch": patch})

            if (i + 1) % 500 == 0:
                await session.commit()
                print(f"  [{i+1}/{len(all_updates)}] committed")

        await session.commit()

        # Final stats
        result = await session.execute(text("""
            SELECT count(*) FILTER (WHERE (properties->>'latitude') IS NOT NULL) as has_coords,
                   count(*) FILTER (WHERE (properties->>'latitude') IS NULL) as no_coords
            FROM kg_entities WHERE entity_type='person'
        """))
        row = result.fetchone()
        print(f"\n{'='*60}")
        print(f"Results:")
        print(f"  Description match: {stats['matched']}")
        print(f"  Teacher propagation: {len(teacher_updates)}")
        print(f"  Total new coords: {len(all_updates)}")
        print(f"  Persons with coords now: {row[0]}")
        print(f"  Persons without coords: {row[1]}")
        print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
