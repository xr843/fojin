"""Delete secular persons (actors, politicians, athletes) imported by mistake."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    with open("data/persons_delete_final.json") as f:
        qids = json.load(f)
    print(f"Loaded {len(qids)} Wikidata IDs to delete")

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as session:
        # Find entity IDs matching these Q-IDs
        result = await session.execute(text("""
            SELECT id, name_zh FROM kg_entities
            WHERE entity_type = 'person'
              AND external_ids->>'wikidata' = ANY(:qids)
        """), {"qids": qids})
        rows = result.fetchall()
        print(f"Matched {len(rows)} person entities in KG")

        ids = [r[0] for r in rows]
        print("\nSample to delete:")
        for r in rows[:15]:
            print(f"  #{r[0]} {r[1]}")

        # Delete relations first, then entities
        if ids:
            await session.execute(text("""
                DELETE FROM kg_relations WHERE subject_id = ANY(:ids) OR object_id = ANY(:ids)
            """), {"ids": ids})

            batch = 200
            for i in range(0, len(ids), batch):
                await session.execute(text("""
                    DELETE FROM kg_entities WHERE id = ANY(:ids)
                """), {"ids": ids[i:i+batch]})
            await session.commit()
            print(f"\nDeleted {len(ids)} secular persons")

    await engine.dispose()

asyncio.run(main())
