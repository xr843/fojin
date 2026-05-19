"""
Import Tibetan Buddhist places from BDRC into the FoJin knowledge graph.

Reads backend/data/bdrc_places.json (produced by fetch_bdrc_places.py).
For each BDRC place:
  1. Look up existing KGEntity by external_ids->>'bdrc' to avoid re-import.
  2. Look up by normalized Chinese name among existing monastery/place entities.
     If found AND lacks coordinates: enrich it (add lat/lng + bdrc id).
  3. Otherwise create a new KGEntity with entity_type='monastery' (or 'place' for
     pilgrimage sites), storing lat/lng/bdrc_id/placeType.

All coordinates come from BDRC's bdo:placeLat / bdo:placeLong — no synthesis.

Usage:
    cd backend
    python -m scripts.import_bdrc_places --dry-run
    python -m scripts.import_bdrc_places
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.knowledge_graph import KGEntity

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "bdrc_places.json"

# Map BDRC placeType -> FoJin entity_type
PLACE_TYPE_TO_ENTITY_TYPE = {
    "PT0037": "monastery",
    "PT0038": "monastery",
    "PT0040": "monastery",
    "PT0050": "monastery",
    "PT0053": "place",          # pilgrimage site
    "PT0064": "monastery",      # retreat center
}


def normalize_zh(s: str | None) -> str:
    if not s:
        return ""
    return s.strip().replace(" ", "").replace("　", "")


async def import_bdrc_places(
    session: AsyncSession,
    records: list[dict],
    dry_run: bool,
) -> dict:
    """Match BDRC records to KG entities; enrich or create as needed."""
    stats = {
        "already_imported": 0,   # matched by external_ids.bdrc
        "enriched_zh_match": 0,  # matched existing by name_zh, added coords
        "created": 0,            # new KGEntity
        "skipped": 0,
    }

    # Preload existing entities of relevant types (avoid N queries)
    result = await session.execute(
        select(KGEntity).where(
            KGEntity.entity_type.in_(["monastery", "place"]),
        )
    )
    existing = list(result.scalars().all())

    by_bdrc: dict[str, KGEntity] = {}
    by_zh: dict[str, list[KGEntity]] = {}
    for e in existing:
        ext = e.external_ids or {}
        if ext.get("bdrc"):
            by_bdrc[ext["bdrc"]] = e
        key = normalize_zh(e.name_zh)
        if key:
            by_zh.setdefault(key, []).append(e)

    for rec in records:
        bdrc_id = rec["bdrc_id"]
        name_zh = rec.get("name_zh")
        name_bo = rec.get("name_bo")
        name_en = rec.get("name_en")
        lat = rec["lat"]
        lng = rec["lng"]
        place_type = rec.get("place_type", "")
        entity_type = PLACE_TYPE_TO_ENTITY_TYPE.get(place_type, "monastery")

        # Dedupe: already imported by BDRC id
        if bdrc_id in by_bdrc:
            stats["already_imported"] += 1
            continue

        # Try enrich by Chinese-name match
        candidates = by_zh.get(normalize_zh(name_zh), []) if name_zh else []
        if candidates:
            # Enrich first candidate of type 'monastery' or 'place' that lacks coords
            target = None
            for c in candidates:
                props = c.properties or {}
                if not props.get("latitude"):
                    target = c
                    break
            if target is None:
                # All already have coords -> still stamp the bdrc id on first for provenance
                target = candidates[0]

            props = dict(target.properties or {})
            ext = dict(target.external_ids or {})
            ext["bdrc"] = bdrc_id
            if not props.get("latitude"):
                props["latitude"] = lat
                props["longitude"] = lng
                props["geo_source"] = "bdrc"
            if name_bo and not target.name_bo:
                target.name_bo = name_bo
            if name_en and not target.name_en:
                target.name_en = name_en
            if not dry_run:
                target.properties = props
                target.external_ids = ext
            stats["enriched_zh_match"] += 1
            by_bdrc[bdrc_id] = target
            if stats["enriched_zh_match"] <= 20:
                print(
                    f"  ~ enriched '{target.name_zh}' ({target.entity_type}) "
                    f"<- BDRC {bdrc_id} ({lat:.4f},{lng:.4f})"
                )
            continue

        # Create new entity
        # Use name_zh if available, else name_en, else Wylie name_bo with '(Wylie)' tag
        primary_name = name_zh or name_en or (name_bo or "").rstrip("/").strip()
        if not primary_name:
            stats["skipped"] += 1
            continue

        new_entity = KGEntity(
            entity_type=entity_type,
            name_zh=primary_name,
            name_bo=name_bo,
            name_en=name_en,
            properties={
                "latitude": lat,
                "longitude": lng,
                "geo_source": "bdrc",
                "bdrc_place_type": place_type,
                "bdrc_place_type_label": rec.get("place_type_label"),
            },
            external_ids={"bdrc": bdrc_id},
        )
        if not dry_run:
            session.add(new_entity)
        stats["created"] += 1
        if stats["created"] <= 20:
            print(
                f"  + created {entity_type:10s} '{primary_name}' "
                f"[bo={name_bo!r}] ({lat:.4f},{lng:.4f}) BDRC:{bdrc_id}"
            )

    return stats


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-file", default=str(DATA_FILE))
    parser.add_argument("--limit", type=int, default=0, help="limit records (0=all)")
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin - BDRC Tibetan Places Importer")
    print("=" * 60)

    data_path = Path(args.data_file)
    if not data_path.exists():
        print(f"ERROR: data file not found: {data_path}")
        print("Run: python scripts/fetch_bdrc_places.py first (on your local machine)")
        sys.exit(1)

    with data_path.open(encoding="utf-8") as f:
        records = json.load(f)
    if args.limit > 0:
        records = records[: args.limit]
    print(f"Loaded {len(records)} BDRC records from {data_path}")
    if args.dry_run:
        print("DRY RUN - no changes will be written\n")

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        stats = await import_bdrc_places(session, records, args.dry_run)
        if not args.dry_run:
            await session.commit()

    await engine.dispose()

    print("\n" + "=" * 60)
    print("Results:")
    for k, v in stats.items():
        print(f"  {k:20s} {v}")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN complete - no changes written")
    else:
        print("Committed.")


if __name__ == "__main__":
    asyncio.run(main())
