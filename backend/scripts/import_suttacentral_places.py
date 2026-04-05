"""
Import Theravada / Pali-canon geographic places into the KG.

Data source: Wikidata (queried via SPARQL + wbsearchentities, see
  scripts/fetch_theravada_places.py). Canonical Nikaya places
  (舍卫城、王舍城、祇园精舍、竹林精舍、迦毗罗卫 等) are curated by hand-
  verified Q-IDs. Regional places (Sri Lanka/Myanmar/Thailand/Cambodia/
  Laos/India/Nepal/Bangladesh monasteries, temples, stupas, pagodas)
  come from broad SPARQL queries bounded by P17 (country).

All records carry a Wikidata Q-ID for provenance. No synthetic data.

Input: data/suttacentral_places.json
  [{"wikidata_id":"Q...","name_en":"...","name_zh":"...","name_pi":"...",
    "name_sa":"...","latitude":..,"longitude":..,"country":"..",
    "source":"wikidata:nikaya_canonical"|"wikidata:theravada_region",
    "description":"..."}, ...]

Matching strategy:
1. Match existing KG entities by wikidata_id in external_ids -> enrich coords.
2. Match by normalized name_zh / name_en -> enrich coords + add wikidata Q-ID.
3. Create NEW entities (entity_type='place') for unmatched records.

Usage:
    cd backend
    python -m scripts.import_suttacentral_places --dry-run
    python -m scripts.import_suttacentral_places
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

INPUT = "data/suttacentral_places.json"


def norm_zh(s: str | None) -> str:
    return (s or "").strip().replace(" ", "").replace("（", "(").replace("）", ")")


def norm_en(s: str | None) -> str:
    return (s or "").strip().lower()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input", default=INPUT)
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 (FoJin) — SuttaCentral / Theravada Places Importer")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN — no database writes\n")

    with open(args.input, encoding="utf-8") as f:
        records: list[dict] = json.load(f)
    print(f"Loaded {len(records)} place records from {args.input}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        result = await session.execute(select(KGEntity))
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} KG entities")

        # Build lookup indexes
        by_qid: dict[str, list[KGEntity]] = {}
        by_zh: dict[str, list[KGEntity]] = {}
        by_en: dict[str, list[KGEntity]] = {}
        by_sa: dict[str, list[KGEntity]] = {}
        by_pi: dict[str, list[KGEntity]] = {}

        for e in entities:
            if e.external_ids and isinstance(e.external_ids, dict):
                wqid = e.external_ids.get("wikidata")
                if wqid:
                    by_qid.setdefault(wqid, []).append(e)
            if e.name_zh:
                by_zh.setdefault(norm_zh(e.name_zh), []).append(e)
            if e.name_en:
                by_en.setdefault(norm_en(e.name_en), []).append(e)
            if e.name_sa:
                by_sa.setdefault(norm_en(e.name_sa), []).append(e)
            if e.name_pi:
                by_pi.setdefault(norm_en(e.name_pi), []).append(e)

        matched_qid = 0
        matched_name = 0
        updated_coord = 0
        created = 0

        for rec in records:
            qid = rec.get("wikidata_id")
            if not qid:
                continue

            lat = rec.get("latitude")
            lng = rec.get("longitude")
            if lat is None or lng is None:
                continue

            name_zh = rec.get("name_zh") or ""
            name_en = rec.get("name_en") or ""
            name_pi = rec.get("name_pi") or ""
            name_sa = rec.get("name_sa") or ""
            src_tag = rec.get("source", "wikidata:theravada")
            country = rec.get("country") or ""
            desc = rec.get("description") or ""

            # 1. Match by wikidata Q-ID
            candidates = by_qid.get(qid, [])
            via = "qid"

            # 2. Match by zh name (exact-normalized)
            if not candidates and name_zh:
                candidates = by_zh.get(norm_zh(name_zh), [])
                if candidates:
                    via = "name_zh"

            # 3. Match by en name
            if not candidates and name_en:
                candidates = by_en.get(norm_en(name_en), [])
                if candidates:
                    via = "name_en"

            # 4. Match by pi/sa
            if not candidates and name_pi:
                candidates = by_pi.get(norm_en(name_pi), [])
                if candidates:
                    via = "name_pi"

            if candidates:
                if via == "qid":
                    matched_qid += 1
                else:
                    matched_name += 1
                for entity in candidates:
                    props = dict(entity.properties or {})
                    ext_ids = dict(entity.external_ids or {})
                    changed = False
                    if not props.get("latitude"):
                        props["latitude"] = lat
                        props["longitude"] = lng
                        props["geo_source"] = src_tag
                        changed = True
                    if not ext_ids.get("wikidata"):
                        ext_ids["wikidata"] = qid
                        changed = True
                    if changed:
                        if not args.dry_run:
                            entity.properties = props
                            entity.external_ids = ext_ids
                        updated_coord += 1
                        if updated_coord <= 20:
                            print(f"  ~ MATCH[{via}] {entity.name_zh or entity.name_en} "
                                  f"← ({lat:.4f},{lng:.4f}) [{qid}]")
                continue

            # 5. No match — create new entity
            if not name_zh and not name_en:
                continue  # skip unlabeled
            primary_zh = name_zh or name_en
            new_entity = KGEntity(
                entity_type="place",
                name_zh=primary_zh,
                name_en=name_en or None,
                name_pi=name_pi or None,
                name_sa=name_sa or None,
                description=desc or None,
                properties={
                    "latitude": lat,
                    "longitude": lng,
                    "geo_source": src_tag,
                    "country": country,
                    "tradition": "theravada",
                },
                external_ids={"wikidata": qid},
            )
            if not args.dry_run:
                session.add(new_entity)
            created += 1
            if created <= 30:
                print(f"  + NEW {primary_zh} / {name_en} "
                      f"({lat:.4f},{lng:.4f}) [{qid}] {country}")

            if created % 100 == 0 and not args.dry_run:
                await session.flush()

        if created > 30:
            print(f"  ... and {created - 30} more new entities")

        if not args.dry_run:
            await session.commit()
            print("\nCommitted to database.")
        else:
            print("\nDry-run complete — nothing written.")

        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  matched by wikidata_id : {matched_qid}")
        print(f"  matched by name        : {matched_name}")
        print(f"  enriched w/ coords     : {updated_coord}")
        print(f"  NEW entities created   : {created}")
        print(f"  total records input    : {len(records)}")
        print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
