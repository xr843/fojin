"""Import Treasury of Lives + Wikidata extended Buddhist persons.

Only imports persons with real coordinates. Matches by Wikidata Q-ID first.
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


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Load both datasets
    with open("data/treasury_of_lives.json", encoding="utf-8") as f:
        tol_records = json.load(f)
    with open("data/wikidata_persons_extended.json", encoding="utf-8") as f:
        wde_records = json.load(f)

    # Filter: only those with coordinates
    tol_with_coords = [r for r in tol_records if r.get("latitude") and r.get("longitude")]
    wde_with_coords = [r for r in wde_records if r.get("latitude") and r.get("longitude")]

    print(f"TOL records: {len(tol_records)} total, {len(tol_with_coords)} with coords")
    print(f"Wikidata extended: {len(wde_records)} total, {len(wde_with_coords)} with coords")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Load existing persons by Wikidata ID
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type == "person")
        )
        existing = list(result.scalars().all())
        by_wikidata = {}
        by_name = {}
        for e in existing:
            ext = e.external_ids or {}
            if ext.get("wikidata"):
                by_wikidata[ext["wikidata"]] = e
            if e.name_zh:
                by_name.setdefault(normalize(e.name_zh), []).append(e)

        print(f"Loaded {len(existing)} existing person entities\n")

        stats = {
            "tol_matched_wikidata": 0,
            "tol_matched_name": 0,
            "tol_enriched": 0,
            "tol_created": 0,
            "wde_matched_wikidata": 0,
            "wde_matched_name": 0,
            "wde_enriched": 0,
            "wde_created": 0,
        }

        # --- Import Treasury of Lives (311 with coords) ---
        print("[Phase 1] Treasury of Lives persons with coordinates...")
        for rec in tol_with_coords:
            wid = rec.get("wikidata_id")
            name_zh = rec.get("name_zh") or rec.get("name_bo") or rec.get("name_en", "")
            if not name_zh:
                continue
            lat, lng = rec["latitude"], rec["longitude"]

            # Try match
            entity = None
            match_type = None
            if wid and wid in by_wikidata:
                entity = by_wikidata[wid]
                match_type = "tol_matched_wikidata"
            elif name_zh:
                cands = by_name.get(normalize(name_zh), [])
                if cands:
                    entity = cands[0]
                    match_type = "tol_matched_name"

            if entity:
                stats[match_type] += 1
                # Enrich metadata
                props = dict(entity.properties or {})
                updated = False
                if not props.get("latitude"):
                    props["latitude"] = lat
                    props["longitude"] = lng
                    props["geo_source"] = "treasury_of_lives"
                    updated = True
                for field in ["birth_year", "death_year", "tradition", "name_bo", "tol_url"]:
                    if rec.get(field) and not props.get(field):
                        props[field] = rec[field]
                        updated = True
                if updated:
                    if not args.dry_run:
                        entity.properties = props
                    stats["tol_enriched"] += 1
                continue

            # Create new
            props = {
                "latitude": lat,
                "longitude": lng,
                "geo_source": "treasury_of_lives",
                "tol_url": rec.get("tol_url"),
            }
            if rec.get("birth_year"):
                props["year_start"] = rec["birth_year"]
                props["birth_year"] = rec["birth_year"]
            if rec.get("death_year"):
                props["year_end"] = rec["death_year"]
                props["death_year"] = rec["death_year"]
            if rec.get("tradition"):
                props["tradition"] = rec["tradition"]
            if rec.get("name_bo"):
                props["name_bo"] = rec["name_bo"]

            ext_ids = {}
            if wid:
                ext_ids["wikidata"] = wid
            if rec.get("bdrc_person_id"):
                ext_ids["bdrc"] = rec["bdrc_person_id"]
            if rec.get("tol_id"):
                ext_ids["tol"] = rec["tol_id"]

            new_entity = KGEntity(
                entity_type="person",
                name_zh=name_zh,
                name_en=rec.get("name_en") or None,
                name_bo=rec.get("name_bo") or None,
                properties=props,
                external_ids=ext_ids,
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["tol_created"] += 1

        # --- Import Wikidata Extended (23 founders) ---
        print("\n[Phase 2] Wikidata extended Buddhist founders...")
        for rec in wde_with_coords:
            wid = rec.get("wikidata_id")
            name_zh = rec.get("name_zh") or rec.get("name_ja") or rec.get("name_en", "")
            if not name_zh:
                continue
            lat, lng = rec["latitude"], rec["longitude"]

            entity = None
            match_type = None
            if wid and wid in by_wikidata:
                entity = by_wikidata[wid]
                match_type = "wde_matched_wikidata"
            elif name_zh:
                cands = by_name.get(normalize(name_zh), [])
                if cands:
                    entity = cands[0]
                    match_type = "wde_matched_name"

            if entity:
                stats[match_type] += 1
                props = dict(entity.properties or {})
                if not props.get("latitude"):
                    props["latitude"] = lat
                    props["longitude"] = lng
                    props["geo_source"] = f"wikidata:founder:{rec.get('source_query','')}"
                    if not args.dry_run:
                        entity.properties = props
                    stats["wde_enriched"] += 1
                continue

            # Create new
            props = {
                "latitude": lat,
                "longitude": lng,
                "geo_source": f"wikidata:founder:{rec.get('source_query','')}",
            }
            if rec.get("birth_year"):
                props["year_start"] = rec["birth_year"]
                props["birth_year"] = rec["birth_year"]
            if rec.get("death_year"):
                props["year_end"] = rec["death_year"]
                props["death_year"] = rec["death_year"]

            new_entity = KGEntity(
                entity_type="person",
                name_zh=name_zh,
                name_en=rec.get("name_en") or None,
                properties=props,
                external_ids={"wikidata": wid} if wid else {},
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["wde_created"] += 1

        if not args.dry_run:
            await session.commit()

        print("\n" + "=" * 60)
        print("Results:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
