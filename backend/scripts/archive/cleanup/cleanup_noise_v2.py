"""Stricter cleanup: remove secular/political persons and more noise patterns."""
import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

# Additional noise patterns
NOISE_PATTERNS_V2 = [
    "皇宫", "皇宮", "palace", "故宫",
    "城堡", "castle", "fortress",
    "火车站", "車站", "station", "railway",
    "school", "学校", "學校",
    "church", "教堂", "天主教堂", "cathedral",
    "mosque", "清真寺",
    "synagogue", "犹太", "jewish",
    "factory", "工厂", "工廠",
    "farm", "农场", "farm", "botanic",
    "market", "市场",
    "office ", "headquarters", "署 |",
    "theater", "剧院", "劇院",
    "cinema",
    "restaurant", "餐厅",
    "embassy", "使馆", "领事",
    "prison", "监狱",
    "barracks", "兵营",
    "保甲", "衙", "县衙",
    "炮台", "城墙", "城牆",
    "tobacco", "烟厂", "煙廠",
    "cotton", "棉紡",
    "战役", "戰役", "battle of", "siege",  # battle events
    "customs", "稅務",
    "military", "宪兵",
    "postoffice", "郵政", "邮政",
    "preparatory",
    "jinja",  # Shinto shrine (not Buddhist)
    "shinto", "神社", "神宫", "神宮",
]

KEEP_PATTERNS = [
    "佛", "寺", "庙", "廟", "宮 (buddhist)",
    "temple", "monastery", "buddhist", "dharma", "stupa",
    "pagoda", "bodhi", "buddha",
    "院", "庵", "仏", "gompa", "vihara",
]


def has_buddhist_keyword(zh: str, en: str) -> bool:
    combined = f"{zh or ''} {en or ''}".lower()
    strict_kw = ["佛", "寺", "廟", "庙", "dharma", "buddha", "buddhist",
                 "monastery", "gompa", "vihara", "dgon", "stupa", "pagoda",
                 "bodhi", "sangha", "zen ", "禪", "禅寺", "禅院", "仏",
                 "sutra", "arhat", "bhikkhu"]
    return any(k.lower() in combined for k in strict_kw)


def is_v2_noise(zh: str, en: str) -> tuple[bool, str]:
    if has_buddhist_keyword(zh, en):
        return False, ""
    combined = f"{zh or ''} {en or ''}".lower()
    for pat in NOISE_PATTERNS_V2:
        if pat.lower() in combined:
            return True, pat
    return False, ""


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove-persons", action="store_true",
                        help="Also remove wikidata:person entries (too polluted with politicians)")
    args = parser.parse_args()

    print("=" * 60)
    print("Cleanup V2: stricter noise filtering")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Get all wikidata-sourced entities
        result = await session.execute(text("""
            SELECT id, entity_type, name_zh, name_en, properties->>'geo_source'
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (
                properties->>'geo_source' LIKE 'wikidata:%'
                OR properties->>'geo_source' = 'bdrc'
              )
        """))
        rows = result.fetchall()
        print(f"Scanning {len(rows)} entities...\n")

        by_pattern: dict[str, int] = {}
        to_delete: list[int] = []
        person_to_delete: list[int] = []

        for eid, etype, zh, en, source in rows:
            is_n, pat = is_v2_noise(zh, en)
            if is_n:
                by_pattern[pat] = by_pattern.get(pat, 0) + 1
                to_delete.append(eid)
                continue

            # For persons: remove if from wikidata:person/wikidata:birth_place source
            # and no Buddhist keyword in name (these came from too-broad religion=Buddhism query)
            if args.remove_persons and etype == "person" and source and source.startswith("wikidata:"):
                person_to_delete.append(eid)

        print("=== Additional noise patterns ===")
        for pat, cnt in sorted(by_pattern.items(), key=lambda x: -x[1]):
            print(f"  '{pat}': {cnt}")
        print(f"Total by name pattern: {len(to_delete)}")

        if args.remove_persons:
            print(f"Wikidata persons without Buddhist keyword: {len(person_to_delete)}")
            print("  (Remove these: politicians, celebrities tangentially tagged as Buddhist)")

        all_delete = list(set(to_delete + person_to_delete))
        print(f"\nTotal to delete: {len(all_delete)}")

        if not args.dry_run and all_delete:
            await session.execute(text("""
                DELETE FROM kg_relations
                WHERE subject_id = ANY(:ids) OR object_id = ANY(:ids)
            """), {"ids": all_delete})

            batch = 200
            for i in range(0, len(all_delete), batch):
                batch_ids = all_delete[i:i+batch]
                await session.execute(text("""
                    DELETE FROM kg_entities WHERE id = ANY(:ids)
                """), {"ids": batch_ids})

            await session.commit()
            print(f"Deleted {len(all_delete)} entities")
        else:
            print("DRY RUN" if args.dry_run else "Nothing to delete")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
