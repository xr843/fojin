"""Restore all persons from buddhist_persons.json that are missing from DB."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.models.knowledge_graph import KGEntity

async def main():
    with open("data/buddhist_persons.json", encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} records")

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as session:
        # Current Wikidata IDs in DB
        r = await session.execute(text("""
            SELECT external_ids->>'wikidata' FROM kg_entities
            WHERE entity_type='person' AND external_ids->>'wikidata' IS NOT NULL
        """))
        existing = {row[0] for row in r.fetchall()}
        print(f"Existing persons with Wikidata ID: {len(existing)}")

        restored = 0
        for rec in records:
            wid = rec["wikidata_id"]
            if wid in existing:
                continue
            primary = rec.get("name_zh") or rec.get("name_ja") or rec.get("name_en")
            if not primary:
                continue
            place = rec.get("place_name", "")
            e = KGEntity(
                entity_type="person",
                name_zh=primary,
                name_en=rec.get("name_en") or None,
                properties={
                    "latitude": rec["latitude"],
                    "longitude": rec["longitude"],
                    "geo_source": f"wikidata:birth_place:{place}" if place else "wikidata:person",
                    "source": "wikidata",
                },
                external_ids={"wikidata": wid},
            )
            session.add(e)
            restored += 1
            if restored % 200 == 0:
                await session.flush()
                print(f"  ... restored {restored}")

        await session.commit()
        print(f"\nRestored: {restored} persons")
    await engine.dispose()

asyncio.run(main())
