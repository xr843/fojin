import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # Persons by dynasty without coords
        r = await s.execute(text("""
            SELECT e.properties->>'dynasty' as dynasty, COUNT(*) as cnt
            FROM kg_entities e WHERE e.entity_type='person'
              AND (e.properties->>'latitude') IS NULL
            GROUP BY dynasty ORDER BY cnt DESC LIMIT 20
        """))
        print("Persons WITHOUT coords by dynasty:")
        for row in r.fetchall(): print(f"  {row[0] or '(none)'}: {row[1]}")

        # Persons by properties keys
        r = await s.execute(text("""
            SELECT key, COUNT(*) FROM (
                SELECT jsonb_object_keys(properties::jsonb) as key
                FROM kg_entities WHERE entity_type='person'
                  AND (properties->>'latitude') IS NULL
                LIMIT 5000
            ) sub GROUP BY key ORDER BY COUNT(*) DESC
        """))
        print("\nCommon property keys on persons without coords:")
        for row in r.fetchall(): print(f"  {row[0]}: {row[1]}")

        # Total persons with translated relation (these are translators with dynasty info)
        r = await s.execute(text("""
            SELECT COUNT(DISTINCT r.subject_id) FROM kg_relations r
            JOIN kg_entities e ON e.id=r.subject_id AND e.entity_type='person'
            WHERE r.predicate='translated' AND (e.properties->>'latitude') IS NULL
        """))
        print(f"\nTranslators without coords: {r.scalar()}")

    await engine.dispose()

asyncio.run(main())
