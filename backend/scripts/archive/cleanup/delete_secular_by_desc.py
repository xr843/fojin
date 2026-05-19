"""Delete secular persons based on Wikidata descriptions."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    with open("data/persons_delete_by_desc.json") as f:
        qids = json.load(f)
    print(f"Deleting {len(qids)} secular persons by Wikidata description")

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT id FROM kg_entities
            WHERE entity_type='person' AND external_ids->>'wikidata' = ANY(:q)
        """), {"q": qids})
        ids = [row[0] for row in r.fetchall()]
        print(f"Matched {len(ids)} in DB")

        if ids:
            await s.execute(text("""
                DELETE FROM kg_relations WHERE subject_id=ANY(:i) OR object_id=ANY(:i)
            """), {"i": ids})
            batch = 200
            for i in range(0, len(ids), batch):
                await s.execute(text("""
                    DELETE FROM kg_entities WHERE id = ANY(:i)
                """), {"i": ids[i:i+batch]})
            await s.commit()
            print(f"Deleted {len(ids)}")

    await engine.dispose()

asyncio.run(main())
