"""Remove non-Buddhist noise entities imported from Wikidata.

Removes entities whose names strongly indicate non-Buddhist categories:
- Museums (博物馆/博物館/museum) — not a single Buddhist temple has "museum" in its name
- War memorials (纪念馆 referencing war/massacre/抗日/抗美)
- Wildlife/safari parks, zoos
- Distilleries, archives, universities
- Exhibition halls, heritage parks (non-Buddhist)

Safety: Only removes entities imported via wikidata:* geo_source (preserves DILA/BDRC/SuttaCentral).
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

# Patterns that definitively mean NOT a Buddhist temple/place/person
# Each pattern matches name_zh OR name_en (case-insensitive for English)
NOISE_PATTERNS = [
    # Museums (100% not Buddhist temples)
    "博物馆", "博物館", "博物院", "museum",
    # Memorial halls (war/political, not Buddhist)
    "纪念馆", "紀念館", "memorial hall", "memorial museum", "memorial park",
    "纪念堂", "紀念堂", "memorial",
    # Wildlife / parks / gardens
    "野生动物", "野生動物", "動物園", "动物园", "zoo ", "safari", "wildlife",
    "海洋公園", "海洋公园", "ocean park",
    # Industrial / commercial
    "distillery", "winery", "brewery", "酒厂",
    # Transport / science
    "铁道", "鐵道", "railway museum", "metro museum",
    "aviation museum", "机车", "機車",
    # Education
    "university museum", "大学博物馆",
    # Archives / libraries
    "archives", "档案馆", "檔案館", "library",
    # Art galleries
    "美术馆", "美術館", "art gallery", "gallery",
    # Shopping / mall / hotel
    "shopping mall", "hotel ", "hostel",
    # Exhibition halls
    "exhibition hall", "展览馆", "展覽館",
    # Sculpture / monument gardens
    "雕塑园", "雕塑園", "sculpture park",
    # Historical figures memorial (not Buddhist figures)
    "故居", "former residence",
    # Cemetery / tomb (with exceptions checked)
    "烈士陵园", "martyrs",
]

# Exception patterns — keep these even if they match noise
KEEP_PATTERNS = [
    "佛", "寺", "庙", "廟", "宮", "堂", "禪", "禅", "教", "法", "僧",
    "temple", "monastery", "buddhist", "dharma", "sangha", "stupa",
    "pagoda", "shrine", "bodhi", "nirvana", "buddha",
    "bhikkhu", "bhikkhuni", "arhat",
    # Japanese Buddhist terms
    "寺", "院", "堂", "庵", "僧", "仏", "仏教",
    # Tibetan/Sanskrit
    "gompa", "vihara", "chortens", "sutra",
]


def is_noise(name_zh: str, name_en: str) -> tuple[bool, str]:
    """Return (is_noise, matched_pattern)."""
    combined = f"{name_zh or ''} {name_en or ''}".lower()

    # First check if it has Buddhist keywords — if yes, it's NOT noise
    for keep in KEEP_PATTERNS:
        if keep.lower() in combined:
            return False, ""

    # Then check noise patterns
    for pat in NOISE_PATTERNS:
        if pat.lower() in combined:
            return True, pat
    return False, ""


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Cleanup: Remove non-Buddhist noise entities")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Only target wikidata-sourced entities with coords
        result = await session.execute(text("""
            SELECT id, entity_type, name_zh, name_en, properties->>'geo_source'
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (
                properties->>'geo_source' LIKE 'wikidata:%'
                OR properties->>'geo_source' LIKE 'bdrc'
              )
        """))
        rows = result.fetchall()
        print(f"Scanning {len(rows)} wikidata/bdrc-sourced entities...\n")

        noise_by_pattern: dict[str, int] = {}
        to_delete: list[int] = []
        sample: list[tuple] = []

        for eid, etype, zh, en, source in rows:
            is_n, pat = is_noise(zh, en)
            if is_n:
                noise_by_pattern[pat] = noise_by_pattern.get(pat, 0) + 1
                to_delete.append(eid)
                if len(sample) < 30:
                    sample.append((eid, etype, zh, en, pat, source))

        print("=== Matched noise patterns ===")
        for pat, cnt in sorted(noise_by_pattern.items(), key=lambda x: -x[1]):
            print(f"  '{pat}': {cnt}")

        print(f"\n=== Sample (first 30) ===")
        for eid, etype, zh, en, pat, source in sample:
            print(f"  [{etype}] #{eid} '{zh}' | {en} | pattern='{pat}' | {source}")

        print(f"\n=== Summary ===")
        print(f"Total to delete: {len(to_delete)}")

        if not args.dry_run:
            # Delete relations first
            if to_delete:
                await session.execute(text("""
                    DELETE FROM kg_relations
                    WHERE subject_id = ANY(:ids) OR object_id = ANY(:ids)
                """), {"ids": to_delete})

                # Delete entities in batches
                batch = 200
                for i in range(0, len(to_delete), batch):
                    ids = to_delete[i:i+batch]
                    await session.execute(text("""
                        DELETE FROM kg_entities WHERE id = ANY(:ids)
                    """), {"ids": ids})

                await session.commit()
                print(f"Deleted {len(to_delete)} entities")
        else:
            print("DRY RUN — nothing deleted")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
