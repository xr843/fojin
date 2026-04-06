"""Import Wikidata Buddhist persons into KG.

Filters noise (politicians/generals/diplomats with no Buddhist sect),
deduplicates against existing DB by wikidata QID and name_zh,
then creates new KGEntity records.
"""
import argparse
import asyncio
import json
import os
import re
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

INPUT = "data/wikidata_persons_clean.json"

# Noise keywords in description — skip if matched AND no sect
NOISE_PATTERNS = re.compile(
    r"\b(politician|general|diplomat|ambassador|military officer|"
    r"revolutionary|minister|vice.?premier|premier|president|"
    r"actor|actress|singer|footballer|basketball|athlete|"
    r"businessm|entrepreneur|ceo|"
    r"writer(?! .*(buddhis|dharma|sutra))|novelist|"
    r"journalist|photographer|"
    r"chemist|physicist|mathematician|engineer|"
    r"People'?s Republic of China)\b",
    re.IGNORECASE,
)


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


def zh_variants(s: str) -> set[str]:
    variants = {s}
    if HAS_OPENCC and s:
        variants.add(_s2t.convert(s))
        variants.add(_t2s.convert(s))
    return variants


def is_noise(rec: dict) -> bool:
    """Return True if this person is likely not Buddhist."""
    desc = rec.get("description", "") or ""
    sect = rec.get("properties", {}).get("sect")
    source_queries = rec.get("properties", {}).get("source_queries", [])

    # If they have a Buddhist sect, keep them regardless
    # But filter out non-Buddhist "sects" (Wikidata artifacts)
    non_buddhist_sects = {"28 Bolsheviks", "28 bolsheviks"}
    if sect and sect not in non_buddhist_sects:
        return False

    # If description contains noise keywords, filter out
    if NOISE_PATTERNS.search(desc):
        return True

    # If only source is occupation-based query and no sect, be suspicious
    # but still keep — they might be legitimate
    return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Loading {INPUT}...")
    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)
    records = data["persons"]
    print(f"Loaded {len(records)} Wikidata person records")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Load existing persons
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type == "person")
        )
        persons = list(result.scalars().all())
        print(f"Existing DB: {len(persons)} person entities")

        # Build dedup indexes
        by_wikidata: dict[str, KGEntity] = {}
        by_zh: dict[str, KGEntity] = {}

        for p in persons:
            ext = p.external_ids or {}
            wid = ext.get("wikidata")
            if wid:
                by_wikidata[wid] = p
            if p.name_zh:
                for v in zh_variants(normalize(p.name_zh)):
                    by_zh[v] = p

        stats = {
            "total": len(records),
            "filtered_noise": 0,
            "dedup_wikidata": 0,
            "dedup_name_zh": 0,
            "enriched": 0,
            "created": 0,
            "skipped_no_name": 0,
        }

        for rec in records:
            wid = rec["external_ids"]["wikidata"]
            name_zh = rec.get("name_zh", "")
            name_en = rec.get("name_en", "")
            props = rec.get("properties", {})

            # Step 1: Filter noise
            if is_noise(rec):
                stats["filtered_noise"] += 1
                continue

            # Step 2: Dedup by wikidata QID
            existing = by_wikidata.get(wid)
            if existing:
                stats["dedup_wikidata"] += 1
                # Enrich: add wikidata birth/death years if missing
                ep = dict(existing.properties or {})
                changed = False
                if not ep.get("year_start") and props.get("birth_year"):
                    ep["year_start"] = props["birth_year"]
                    changed = True
                if not ep.get("year_end") and props.get("death_year"):
                    ep["year_end"] = props["death_year"]
                    changed = True
                if not ep.get("image_url") and props.get("image_url"):
                    ep["image_url"] = props["image_url"]
                    changed = True
                if changed:
                    stats["enriched"] += 1
                    if not args.dry_run:
                        existing.properties = ep
                continue

            # Step 3: Dedup by name_zh
            if name_zh:
                found = False
                for v in zh_variants(normalize(name_zh)):
                    if v in by_zh:
                        stats["dedup_name_zh"] += 1
                        existing = by_zh[v]
                        # Add wikidata ID to existing
                        ext_ids = dict(existing.external_ids or {})
                        if not ext_ids.get("wikidata"):
                            ext_ids["wikidata"] = wid
                            if not args.dry_run:
                                existing.external_ids = ext_ids
                            stats["enriched"] += 1
                        found = True
                        break
                if found:
                    continue

            # Step 4: Create new entity
            primary_name = name_zh or name_en
            if not primary_name:
                stats["skipped_no_name"] += 1
                continue

            new_props = {
                "source": "wikidata",
            }
            if props.get("birth_year"):
                new_props["year_start"] = props["birth_year"]
            if props.get("death_year"):
                new_props["year_end"] = props["death_year"]
            if props.get("birth_place_lat"):
                new_props["latitude"] = props["birth_place_lat"]
                new_props["longitude"] = props["birth_place_lng"]
                new_props["geo_source"] = f"wikidata:birth_place:{props.get('birth_place', '')}"
            if props.get("sect"):
                new_props["sect"] = props["sect"]
            if props.get("image_url"):
                new_props["image_url"] = props["image_url"]
            if props.get("teachers"):
                new_props["teachers"] = props["teachers"]
            if props.get("students"):
                new_props["students"] = props["students"]

            new_entity = KGEntity(
                entity_type="person",
                name_zh=name_zh or name_en,  # name_zh is NOT NULL in DB
                name_en=name_en or None,
                properties=new_props,
                external_ids=rec.get("external_ids", {}),
            )
            if not args.dry_run:
                session.add(new_entity)

            # Add to dedup index so we don't create duplicates within this batch
            by_wikidata[wid] = new_entity
            if name_zh:
                for v in zh_variants(normalize(name_zh)):
                    by_zh[v] = new_entity

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
        mode = "DRY RUN" if args.dry_run else "COMMITTED"
        print(f"Mode: {mode}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
