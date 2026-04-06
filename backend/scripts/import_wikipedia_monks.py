"""Import Wikipedia Chinese monks into KG.

Loads data/wikipedia_monks.json, filters noise by categories,
deduplicates against existing DB by wikidata QID and name_zh,
enriches matched records, creates new KGEntity for unmatched.
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

INPUT = os.path.join(os.path.dirname(__file__), "data", "wikipedia_monks.json")

# Categories must contain at least one of these keywords
BUDDHIST_KEYWORDS = {"僧", "出家", "宗", "佛", "法师", "和尚", "禅师", "上人", "大师"}


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "")


def zh_variants(s: str) -> set[str]:
    variants = {s}
    if HAS_OPENCC and s:
        variants.add(_s2t.convert(s))
        variants.add(_t2s.convert(s))
    return variants


def is_buddhist(rec: dict) -> bool:
    """Return True if categories contain any Buddhist keyword."""
    cats = rec.get("categories", []) or []
    cat_str = "".join(cats)
    return any(kw in cat_str for kw in BUDDHIST_KEYWORDS)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Loading {INPUT}...")
    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data)} Wikipedia monk records")

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
            "total": len(data),
            "filtered_noise": 0,
            "dedup_wikidata": 0,
            "dedup_name_zh": 0,
            "enriched": 0,
            "created": 0,
            "skipped_no_name": 0,
        }

        for rec in data:
            name = (rec.get("name") or "").strip()
            dynasty = rec.get("dynasty")
            school = rec.get("school")
            qid = rec.get("wikidata_qid")
            extract = rec.get("extract", "") or ""
            source_url = rec.get("source_url", "")

            # Step 1: Filter noise by categories
            if not is_buddhist(rec):
                stats["filtered_noise"] += 1
                continue

            if not name:
                stats["skipped_no_name"] += 1
                continue

            # Step 2: Dedup by wikidata QID
            if qid and qid in by_wikidata:
                stats["dedup_wikidata"] += 1
                existing = by_wikidata[qid]
                # Enrich if missing dynasty/school/description
                ep = dict(existing.properties or {})
                changed = False
                if not ep.get("dynasty") and dynasty:
                    ep["dynasty"] = dynasty
                    changed = True
                if not ep.get("school") and school:
                    ep["school"] = school
                    changed = True
                if not existing.description and extract:
                    if not args.dry_run:
                        existing.description = extract[:500]
                    changed = True
                if changed:
                    stats["enriched"] += 1
                    if not args.dry_run:
                        existing.properties = ep
                continue

            # Step 3: Dedup by name_zh
            found = False
            for v in zh_variants(normalize(name)):
                if v in by_zh:
                    stats["dedup_name_zh"] += 1
                    existing = by_zh[v]
                    # Enrich: add wikidata + missing fields
                    ext_ids = dict(existing.external_ids or {})
                    ep = dict(existing.properties or {})
                    changed = False
                    if qid and not ext_ids.get("wikidata"):
                        ext_ids["wikidata"] = qid
                        if not args.dry_run:
                            existing.external_ids = ext_ids
                        changed = True
                    if not ep.get("dynasty") and dynasty:
                        ep["dynasty"] = dynasty
                        changed = True
                    if not ep.get("school") and school:
                        ep["school"] = school
                        changed = True
                    if not existing.description and extract:
                        if not args.dry_run:
                            existing.description = extract[:500]
                        changed = True
                    if changed:
                        stats["enriched"] += 1
                        if not args.dry_run:
                            existing.properties = ep
                    found = True
                    break
            if found:
                continue

            # Step 4: Create new entity
            new_props = {
                "source": "wikipedia:zh",
            }
            if dynasty:
                new_props["dynasty"] = dynasty
            if school:
                new_props["school"] = school

            new_ext = {}
            if qid:
                new_ext["wikidata"] = qid
            if source_url:
                new_ext["wikipedia_zh"] = source_url

            new_entity = KGEntity(
                entity_type="person",
                name_zh=name,
                description=extract[:500] if extract else None,
                properties=new_props,
                external_ids=new_ext,
            )
            if not args.dry_run:
                session.add(new_entity)

            # Add to dedup index
            if qid:
                by_wikidata[qid] = new_entity
            for v in zh_variants(normalize(name)):
                by_zh[v] = new_entity

            stats["created"] += 1
            if stats["created"] % 200 == 0:
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
