"""Export all Wikidata Q-IDs from geo-entities to JSON."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT DISTINCT external_ids->>'wikidata' FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        qids = sorted([row[0] for row in r.fetchall() if row[0]])
    await engine.dispose()
    with open("/data/geo_qids.json", "w") as f:
        json.dump(qids, f)
    print(f"Exported {len(qids)} Q-IDs")

asyncio.run(main())
