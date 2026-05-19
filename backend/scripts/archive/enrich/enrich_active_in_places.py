"""
Backfill coordinates for active_in target places, then re-propagate to persons.

Background (2026-04-04 audit):
    - KG has 373 active_in relations, 122 unique targets
    - 112 targets are place entities (all already have coords)
    - 10 targets are dynasty entities (唐, 南朝, 十六國, etc.) — SKIPPED per project rules
      (dynasty → capital inference is banned as speculative)
    - 0 place entities in KG lack coordinates

Therefore the original "backfill" task is structurally DONE — nothing to backfill.

This script is kept as an idempotent audit + correction importer:
    1. Apply any corrections from data/active_in_place_coords.json (verified vs Wikidata)
    2. Re-run active_in propagation (inherit coords from place to person)

Usage:
    cd backend
    python -m scripts.enrich_active_in_places [--dry-run]
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

INPUT = "data/active_in_place_coords.json"


async def apply_corrections(session: AsyncSession, corrections: list[dict], dry_run: bool) -> int:
    count = 0
    for c in corrections:
        entity = await session.get(KGEntity, c["entity_id"])
        if not entity:
            print(f"  ! entity id={c['entity_id']} not found, skipping")
            continue
        if entity.name_zh != c["name_zh"]:
            print(f"  ! entity id={c['entity_id']} name mismatch: "
                  f"expected {c['name_zh']}, got {entity.name_zh} — skipping")
            continue

        props = dict(entity.properties or {})
        old_lat = props.get("latitude")
        old_lng = props.get("longitude")
        props["latitude"] = c["new_lat"]
        props["longitude"] = c["new_lng"]
        props["geo_source"] = c.get("geo_source", "wikidata:corrected")

        ext_ids = dict(entity.external_ids or {})
        ext_ids["wikidata"] = c["wikidata_id"]

        print(f"  CORRECT {entity.name_zh} (id={entity.id}): "
              f"({old_lat}, {old_lng}) -> ({c['new_lat']}, {c['new_lng']}) "
              f"[{c['wikidata_id']}]")
        print(f"    reason: {c['reason']}")

        if not dry_run:
            entity.properties = props
            entity.external_ids = ext_ids
        count += 1
    return count


async def apply_new_additions(session: AsyncSession, additions: list[dict], dry_run: bool) -> int:
    """Update existing place entities that lack coords, given a list of name->coord mappings."""
    count = 0
    for a in additions:
        entity = await session.get(KGEntity, a["entity_id"])
        if not entity:
            print(f"  ! entity id={a['entity_id']} not found, skipping")
            continue
        props = dict(entity.properties or {})
        if props.get("latitude"):
            print(f"  - {entity.name_zh} already has coords, skipping")
            continue
        props["latitude"] = a["lat"]
        props["longitude"] = a["lng"]
        props["geo_source"] = a.get("geo_source", "wikidata:active_in")
        ext_ids = dict(entity.external_ids or {})
        ext_ids["wikidata"] = a["wikidata_id"]
        print(f"  + {entity.name_zh} ← ({a['lat']:.4f}, {a['lng']:.4f}) [{a['wikidata_id']}]")
        if not dry_run:
            entity.properties = props
            entity.external_ids = ext_ids
        count += 1
    return count


async def propagate_active_in(session: AsyncSession, dry_run: bool) -> int:
    sql = """
        SELECT DISTINCT ON (p.id)
            p.id, pl.name_zh,
            (pl.properties->>'latitude')::float,
            (pl.properties->>'longitude')::float
        FROM kg_entities p
        JOIN kg_relations r ON r.subject_id = p.id AND r.predicate = 'active_in'
        JOIN kg_entities pl ON pl.id = r.object_id
        WHERE p.entity_type = 'person'
          AND (p.properties->>'latitude') IS NULL
          AND (pl.properties->>'latitude') IS NOT NULL
        ORDER BY p.id, r.confidence DESC
    """
    result = await session.execute(text(sql))
    rows = result.fetchall()
    count = 0
    for person_id, place_name, lat, lng in rows:
        entity = await session.get(KGEntity, person_id)
        if not entity:
            continue
        props = dict(entity.properties or {})
        if props.get("latitude"):
            continue
        props["latitude"] = lat
        props["longitude"] = lng
        props["geo_source"] = f"active_in:{place_name}"
        if not dry_run:
            entity.properties = props
        count += 1
        if count <= 20:
            print(f"  + {entity.name_zh} ← {place_name} ({lat:.4f}, {lng:.4f})")
    if count > 20:
        print(f"  ... and {count - 20} more")
    return count


async def also_update_person_geo_source_for_corrected(
    session: AsyncSession, correction_names: list[str], dry_run: bool
) -> int:
    """After a place coord is corrected, update all person entities whose
    geo_source points at that place to use the new coords."""
    count = 0
    for place_name in correction_names:
        # Fetch place entity
        res = await session.execute(
            text("SELECT id, name_zh, properties FROM kg_entities WHERE name_zh = :n AND entity_type='place'"),
            {"n": place_name},
        )
        rows = res.fetchall()
        if not rows:
            continue
        for pid, pname, pprops in rows:
            lat = pprops.get("latitude") if pprops else None
            lng = pprops.get("longitude") if pprops else None
            if not lat:
                continue
            # Find persons whose geo_source references this place
            res2 = await session.execute(
                text("SELECT id, name_zh, properties FROM kg_entities WHERE entity_type='person' "
                     "AND properties->>'geo_source' = :gs"),
                {"gs": f"active_in:{pname}"},
            )
            persons = res2.fetchall()
            for person_id, person_name, person_props in persons:
                newp = dict(person_props or {})
                newp["latitude"] = lat
                newp["longitude"] = lng
                print(f"  UPDATE person {person_name} (id={person_id}) -> ({lat:.4f}, {lng:.4f})")
                if not dry_run:
                    ent = await session.get(KGEntity, person_id)
                    if ent:
                        ent.properties = newp
                count += 1
    return count


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 — active_in 地点坐标补齐/修正")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN — no database writes\n")

    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)

    corrections = data.get("corrections", [])
    additions = data.get("new_additions", [])
    print(f"Corrections to apply: {len(corrections)}")
    print(f"New additions (place entities to fill): {len(additions)}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        print("\n[1/4] Applying corrections to miscoded places…")
        corr_count = await apply_corrections(session, corrections, args.dry_run)

        print("\n[2/4] Updating person entities whose geo_source references corrected places…")
        correction_names = [c["name_zh"] for c in corrections]
        person_corr = await also_update_person_geo_source_for_corrected(
            session, correction_names, args.dry_run
        )

        print("\n[3/4] Updating place entities that lack coords (new additions)…")
        add_count = await apply_new_additions(session, additions, args.dry_run)

        print("\n[4/4] Propagating active_in coords to persons…")
        prop_count = await propagate_active_in(session, args.dry_run)

        if not args.dry_run:
            await session.commit()
            print("\nCommitted.")
        else:
            print("\nDry run complete — no changes written.")

    await engine.dispose()
    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Place corrections applied: {corr_count}")
    print(f"  Person coords updated (via corrected place): {person_corr}")
    print(f"  New place coords added: {add_count}")
    print(f"  Persons inheriting via active_in: {prop_count}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
