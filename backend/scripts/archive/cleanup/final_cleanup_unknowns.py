"""Final cleanup of 'unknown' persons. Expand keywords + delete rest."""
import argparse
import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

# Expanded Buddhist keywords
BUDDHIST_KEYWORDS = [
    "buddhist", "buddhism", "buddha", "gautama", "tathagata", "shakyamuni", "sakyamuni",
    "佛教", "佛学", "佛陀", "釋迦", "释迦",
    "monk", "nun", "bhikkhu", "bhikkhuni", "sramana", "shramana",
    "僧", "和尚", "法師", "法师", "禪師", "禅师", "禪宗", "禅宗",
    "喇嘛", "活佛", "仁波切", "比丘", "比丘尼", "法王",
    "祖师", "祖師", "高僧", "大師", "大师", "尊者", "上人", "座主",
    "chan master", "zen master", "zen buddhism", "chan buddhism", "zen teacher",
    "tibetan buddhist", "vajrayana", "theravada", "mahayana",
    "pure land", "净土", "淨土", "天台", "华严", "華嚴", "nichiren",
    "唯识", "唯識", "律宗", "密宗", "禪 ", "禅 ", "宗派",
    "dalai lama", "panchen", "karmapa", "rinpoche", "tulku", "lama",
    "班禅", "达赖", "噶玛巴",
    "arhat", "bodhisattva", "dharma ", "sangha", "sutra", "tripitaka",
    "菩薩", "菩萨", "羅漢", "罗汉",
    "buddhist scholar", "buddhist philosopher", "buddhist commentator",
    "buddhist missionary",
    "寺", "禅宗", "founder of the ... (school|sect|order)",
    "abbot", "spiritual teacher", "meditation teacher",
    "bodhidharma", "nichiren shoshu", "soto zen", "rinzai",
    "kagyu", "sakya", "gelug", "nyingma", "bon ",
]


NON_BUDDHIST_RELIGIONS = [
    "christian", "catholic", "protestant", "orthodox",
    "jesuit", "dominican", "franciscan", "benedictine",
    "papal", "archbishop", "bishop", "cardinal", "pope ",
    "nestorian", "church of the east",
    "基督教", "天主教", "东正教", "東正教", "新教", "景教",
    "shinto", "confucian", "jewish", "hindu", "islam", "muslim",
    "神社", "神道", "儒学", "道教",
]

def has_buddhist(desc: str) -> bool:
    d = desc.lower()
    # Exclude if mentions other religions
    if any(kw in d for kw in NON_BUDDHIST_RELIGIONS):
        # Only very strong Buddhist signals override religion exclusion
        strong = ["buddhist ", "buddhism", "lama", "rinpoche", "chan buddhism",
                  "zen buddhism", "佛教", "佛陀", "喇嘛", "仁波切", "禅宗", "禪宗"]
        if not any(kw in d for kw in strong):
            return False
    return any(kw in d for kw in BUDDHIST_KEYWORDS)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Final cleanup: delete unknown (non-Buddhist) persons")

    with open("data/person_descriptions.json") as f:
        descs = json.load(f)

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s:
        r = await s.execute(text("""
            SELECT id, name_zh, external_ids->>'wikidata'
            FROM kg_entities
            WHERE entity_type='person' AND (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
              AND (properties->>'geo_source' LIKE 'wikidata:%')
        """))
        rows = r.fetchall()
        print(f"Scanning {len(rows)} wikidata-sourced persons")

        to_delete = []
        kept_buddhist = 0
        sample_keep = []
        sample_delete = []

        for eid, name, wid in rows:
            d = descs.get(wid, {})
            combined = f"{d.get('en','')} {d.get('zh','')}"
            if not combined.strip():
                # No description — keep (conservative)
                continue
            if has_buddhist(combined):
                kept_buddhist += 1
                if len(sample_keep) < 15:
                    sample_keep.append((name, combined[:80]))
            else:
                to_delete.append(eid)
                if len(sample_delete) < 20:
                    sample_delete.append((name, combined[:80]))

        print(f"\nKeep (Buddhist):  {kept_buddhist}")
        print(f"Delete (secular): {len(to_delete)}")

        print("\n=== Sample KEEP ===")
        for name, desc in sample_keep:
            print(f"  + {name}: {desc}")

        print("\n=== Sample DELETE ===")
        for name, desc in sample_delete:
            print(f"  - {name}: {desc}")

        if not args.dry_run and to_delete:
            await s.execute(text("""
                DELETE FROM kg_relations WHERE subject_id=ANY(:i) OR object_id=ANY(:i)
            """), {"i": to_delete})
            batch = 200
            for i in range(0, len(to_delete), batch):
                await s.execute(text("""
                    DELETE FROM kg_entities WHERE id=ANY(:i)
                """), {"i": to_delete[i:i+batch]})
            await s.commit()
            print(f"\nDeleted {len(to_delete)} non-Buddhist persons")

    await engine.dispose()

asyncio.run(main())
