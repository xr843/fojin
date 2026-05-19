"""Restore mistakenly deleted Buddhist masters, then precisely delete only
the problematic persons from the broad 'religion=Buddhism' SPARQL query.

Problem: my previous cleanup used occupation 'writer/philosopher' as proxy for
'secular', but many Buddhist masters have those occupations too.

Correct strategy: only delete persons whose original source_query was
'buddhism_religion_persons' (P140=Buddhism, too broad) AND who aren't in our
clean set from the stricter P106-based queries.
"""
import argparse
import asyncio
import json
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

    # Load the original persons data
    with open("data/buddhist_persons.json", encoding="utf-8") as f:
        records = json.load(f)

    # Set of Q-IDs from CLEAN queries (P106 = Buddhist clergy)
    clean_qids = set()
    religion_only_qids = set()

    for rec in records:
        src = rec.get("source_query", "")
        if src == "buddhism_religion_persons":
            religion_only_qids.add(rec["wikidata_id"])
        else:
            # These came from P106-based queries (monk/priest/teacher/nun)
            clean_qids.add(rec["wikidata_id"])

    # Overlap: QIDs that appear in BOTH clean and religion queries → keep (clean wins)
    religion_only_qids -= clean_qids

    print(f"Clean (P106 Buddhist clergy): {len(clean_qids)}")
    print(f"Religion-only (broad P140):   {len(religion_only_qids)}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # PHASE 1: Restore persons that were in our data but not in DB
        print("\n[Phase 1] Restoring persons mistakenly deleted...")

        # Get all existing Wikidata person IDs
        r = await session.execute(text("""
            SELECT external_ids->>'wikidata' FROM kg_entities
            WHERE entity_type = 'person'
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        existing_qids = {row[0] for row in r.fetchall()}

        restored = 0
        for rec in records:
            wid = rec["wikidata_id"]
            src = rec.get("source_query", "")

            # Only restore clean P106-sourced persons if missing
            if src == "buddhism_religion_persons":
                continue
            if wid in existing_qids:
                continue

            # Restore
            primary_name = rec.get("name_zh") or rec.get("name_ja") or rec.get("name_en")
            if not primary_name:
                continue

            place_name = rec.get("place_name", "")
            new_entity = KGEntity(
                entity_type="person",
                name_zh=primary_name,
                name_en=rec.get("name_en") or None,
                properties={
                    "latitude": rec["latitude"],
                    "longitude": rec["longitude"],
                    "geo_source": f"wikidata:birth_place:{place_name}" if place_name else "wikidata:person",
                    "source": "wikidata",
                },
                external_ids={"wikidata": wid},
            )
            if not args.dry_run:
                session.add(new_entity)
            restored += 1

            if restored % 200 == 0:
                if not args.dry_run:
                    await session.flush()
                print(f"  ... restored {restored}")

        print(f"Restored: {restored}")

        # PHASE 2: Delete persons from religion_only source
        print("\n[Phase 2] Deleting religion-only persons (from broad P140=Buddhism query)...")

        if religion_only_qids:
            r = await session.execute(text("""
                SELECT id FROM kg_entities
                WHERE entity_type = 'person'
                  AND external_ids->>'wikidata' = ANY(:qids)
            """), {"qids": list(religion_only_qids)})
            to_delete = [row[0] for row in r.fetchall()]
            print(f"Matched {len(to_delete)} religion-only persons to delete")

            if to_delete and not args.dry_run:
                await session.execute(text("""
                    DELETE FROM kg_relations
                    WHERE subject_id = ANY(:ids) OR object_id = ANY(:ids)
                """), {"ids": to_delete})

                batch = 200
                for i in range(0, len(to_delete), batch):
                    await session.execute(text("""
                        DELETE FROM kg_entities WHERE id = ANY(:ids)
                    """), {"ids": to_delete[i:i+batch]})

                print(f"Deleted {len(to_delete)} religion-only persons")

        if not args.dry_run:
            await session.commit()
        else:
            print("\nDRY RUN — nothing committed")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
