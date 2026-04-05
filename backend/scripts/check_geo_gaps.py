"""Quick diagnostic: what geo data is missing."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession)
    async with sf() as s:
        # Total by type
        r = await s.execute(text("SELECT entity_type, COUNT(*) FROM kg_entities GROUP BY entity_type ORDER BY COUNT(*) DESC"))
        print("=== Entity totals ===")
        for row in r.fetchall(): print(f"  {row[0]}: {row[1]}")

        # With coords
        r = await s.execute(text("SELECT entity_type, COUNT(*) FROM kg_entities WHERE (properties->>'latitude') IS NOT NULL GROUP BY entity_type ORDER BY COUNT(*) DESC"))
        print("\n=== With coordinates ===")
        for row in r.fetchall(): print(f"  {row[0]}: {row[1]}")

        # Places without coords - sample
        r = await s.execute(text("SELECT name_zh, name_en FROM kg_entities WHERE entity_type='place' AND (properties->>'latitude') IS NULL LIMIT 15"))
        print("\n=== Places WITHOUT coords (sample) ===")
        for row in r.fetchall(): print(f"  {row[0]} | {row[1]}")

        # Person with active_in to a place WITHOUT coords
        r = await s.execute(text("""
            SELECT COUNT(DISTINCT p.id) FROM kg_entities p
            JOIN kg_relations r ON r.subject_id=p.id AND r.predicate='active_in'
            JOIN kg_entities pl ON pl.id=r.object_id
            WHERE p.entity_type='person' AND (p.properties->>'latitude') IS NULL
              AND (pl.properties->>'latitude') IS NULL
        """))
        print(f"\nPersons with active_in to places WITHOUT coords: {r.scalar()}")

        # Person with active_in to a place WITH coords but person still no coords
        r = await s.execute(text("""
            SELECT COUNT(DISTINCT p.id) FROM kg_entities p
            JOIN kg_relations r ON r.subject_id=p.id AND r.predicate='active_in'
            JOIN kg_entities pl ON pl.id=r.object_id
            WHERE p.entity_type='person' AND (p.properties->>'latitude') IS NULL
              AND (pl.properties->>'latitude') IS NOT NULL
        """))
        print(f"Persons could get coords from active_in (place HAS coords): {r.scalar()}")

        # Dynasty entities
        r = await s.execute(text("SELECT name_zh, properties FROM kg_entities WHERE entity_type='dynasty'"))
        print("\n=== Dynasties ===")
        for row in r.fetchall(): print(f"  {row[0]} | {row[1]}")

        # Top places with most relations (important places)
        r = await s.execute(text("""
            SELECT e.name_zh, e.name_en, COUNT(r.id) as rel_count,
                   (e.properties->>'latitude') IS NOT NULL as has_coord
            FROM kg_entities e
            JOIN kg_relations r ON (r.subject_id=e.id OR r.object_id=e.id)
            WHERE e.entity_type='place'
            GROUP BY e.id, e.name_zh, e.name_en, has_coord
            ORDER BY rel_count DESC LIMIT 20
        """))
        print("\n=== Top 20 most-connected places ===")
        for row in r.fetchall():
            status = "✓" if row[3] else "✗"
            print(f"  {status} {row[0]} ({row[1] or '-'}) — {row[2]} relations")

    await engine.dispose()

asyncio.run(main())
