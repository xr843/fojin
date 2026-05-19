"""Import Buddhist persons from Wikidata.

Strategy:
1. Match by wikidata_id → enrich with coords
2. Match by name_zh (normalize whitespace) → enrich
3. Match by name_ja → enrich
4. Create new person entity with Wikidata provenance

Try traditional/simplified variants for Chinese names.
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

try:
    from opencc import OpenCC
    _s2t = OpenCC("s2t")
    _t2s = OpenCC("t2s")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False

INPUT = "data/buddhist_persons.json"


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


def zh_variants(s: str) -> set[str]:
    """Return set of simplified and traditional variants."""
    variants = {s}
    if HAS_OPENCC and s:
        variants.add(_s2t.convert(s))
        variants.add(_t2s.convert(s))
    return variants


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Loading {INPUT}...")
    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} Buddhist person records")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Load all persons
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type == "person")
        )
        persons = list(result.scalars().all())
        print(f"Loaded {len(persons)} person entities from KG")

        # Build indexes
        by_wikidata: dict[str, KGEntity] = {}
        by_zh: dict[str, list[KGEntity]] = {}
        by_en: dict[str, list[KGEntity]] = {}
        by_ja: dict[str, list[KGEntity]] = {}

        for p in persons:
            ext = p.external_ids or {}
            wid = ext.get("wikidata")
            if wid:
                by_wikidata[wid] = p
            if p.name_zh:
                for v in zh_variants(normalize(p.name_zh)):
                    by_zh.setdefault(v, []).append(p)
            if p.name_en:
                by_en.setdefault(p.name_en.lower().strip(), []).append(p)
            # Japanese names could be in name_zh (same kanji) — no separate field

        stats = {
            "matched_wikidata": 0,
            "matched_name_zh": 0,
            "matched_name_ja": 0,
            "matched_name_en": 0,
            "enriched": 0,
            "created": 0,
            "skipped": 0,
        }

        for rec in records:
            wid = rec["wikidata_id"]
            name_zh = rec.get("name_zh", "")
            name_en = rec.get("name_en", "")
            name_ja = rec.get("name_ja", "")
            lat = rec["latitude"]
            lng = rec["longitude"]
            place_name = rec.get("place_name", "")

            entity = None
            match_type = None

            # 1. Wikidata ID match
            entity = by_wikidata.get(wid)
            if entity:
                match_type = "matched_wikidata"
            # 2. Chinese name match (with variants)
            elif name_zh:
                for v in zh_variants(normalize(name_zh)):
                    candidates = by_zh.get(v, [])
                    if candidates:
                        entity = candidates[0]
                        match_type = "matched_name_zh"
                        break
            # 3. Japanese name match (via name_zh in our KG — often same kanji)
            if not entity and name_ja:
                for v in zh_variants(normalize(name_ja)):
                    candidates = by_zh.get(v, [])
                    if candidates:
                        entity = candidates[0]
                        match_type = "matched_name_ja"
                        break
            # 4. English name match
            if not entity and name_en:
                candidates = by_en.get(name_en.lower().strip(), [])
                if candidates:
                    entity = candidates[0]
                    match_type = "matched_name_en"

            if entity:
                stats[match_type] += 1
                props = dict(entity.properties or {})
                if not props.get("latitude"):
                    props["latitude"] = lat
                    props["longitude"] = lng
                    props["geo_source"] = f"wikidata:birth_place:{place_name}" if place_name else "wikidata:person"
                    ext_ids = dict(entity.external_ids or {})
                    if not ext_ids.get("wikidata"):
                        ext_ids["wikidata"] = wid
                        entity.external_ids = ext_ids
                    if not args.dry_run:
                        entity.properties = props
                    stats["enriched"] += 1
                continue

            # Create new person entity
            primary_name = name_zh or name_ja or name_en
            if not primary_name:
                stats["skipped"] += 1
                continue

            new_entity = KGEntity(
                entity_type="person",
                name_zh=primary_name,
                name_en=name_en or None,
                properties={
                    "latitude": lat,
                    "longitude": lng,
                    "geo_source": f"wikidata:birth_place:{place_name}" if place_name else "wikidata:person",
                    "source": "wikidata",
                },
                external_ids={"wikidata": wid},
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["created"] += 1

            if stats["created"] % 500 == 0:
                if not args.dry_run:
                    await session.flush()
                print(f"  ... created {stats['created']}")

        if not args.dry_run:
            await session.commit()

        print("\n" + "=" * 60)
        print("Results:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print("=" * 60)
        print(f"{'Dry run' if args.dry_run else 'Committed'}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
