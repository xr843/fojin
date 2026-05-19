"""Delete secular scholars/diplomats/politicians still in persons table.

Two-phase cleanup:
1. DELETE: people whose description contains clearly-secular occupations
   (historian, diplomat, orientalist, sinologist, etc.) AND no Buddhist keyword
2. KEEP: anyone with explicit Buddhist clergy signals
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

# Strong Buddhist clergy signals (keep if any present)
BUDDHIST_KEYWORDS = [
    # Direct
    "buddhist", "buddhism", "佛教", "佛学", "佛陀",
    # Clergy
    "monk", "nun", " bhikkhu", " bhikkhuni", "sramana",
    "僧", "和尚", "法師", "法师", "禪師", "禅师", "禪宗", "禅宗",
    "喇嘛", "活佛", "仁波切", "比丘", "比丘尼", "法王",
    "祖师", "祖師", "高僧", "大师", "尊者", "上人",
    # Traditions
    "chan master", "zen master", "zen buddhism", "chan buddhism",
    "tibetan buddhist", "vajrayana", "theravada", "mahayana",
    "pure land", "净土", "淨土", "天台", "华严", "華嚴",
    "唯识", "唯識", "律宗", "密宗", "禪 ", "禅 ",
    # Titles
    "dalai lama", "panchen", "karmapa", "rinpoche", "tulku", "lama",
    "班禅", "达赖", "噶玛巴",
    # Sanskrit/Pali
    "arhat", "bodhisattva", "dharma ", "sangha", "sutra", "tripitaka",
    "菩薩", "菩萨", "羅漢", "罗汉",
    # Roles
    "buddhist scholar", "buddhist philosopher", "buddhist commentator",
    "translator of sutras", "dharma teacher", "patriarch of",
    "founder of ... (zen|buddhist|chan|tibetan|pure land|school)",
    "abbot of", "missionary",
    "compiled the blue cliff", "taught buddhism", "studied buddhism",
]

# Definitely secular (delete if NO Buddhist keyword)
SECULAR_KEYWORDS = [
    # Academics studying religion externally
    "historian", "historiographer", "orientalist", "sinologist",
    "indologist", "tibetologist", "philologist", "egyptologist",
    "ethnologist", "archaeologist", "anthropologist",
    "historian of", "scholar of", "researcher of", "professor of",
    "university teacher", "academic", "dean of", "rector of",
    # Political roles
    "diplomat", "ambassador", "statesman", "statesperson", "politician",
    "minister", "prime minister", "foreign minister", "president of",
    "prime-minister", "chancellor", "senator", "congressman", "congresswoman",
    "mayor", "governor", "vice-president", "vice president",
    # Military
    "general ", "admiral ", "military officer", "lieutenant",
    "colonel", "army", "navy officer",
    # Business/law
    "jurist", "lawyer", "attorney", "judge", "barrister", "legal scholar",
    "businessman", "entrepreneur", "economist", "banker", "merchant",
    # Science
    "biologist", "naturalist", "zoologist", "botanist", "geologist",
    "physicist", "chemist", "mathematician", "astronomer", "geographer",
    "engineer", "inventor", "explorer",
    # Arts (secular)
    "painter", "novelist", "poet of the", "playwright", "musician",
    "composer", "sculptor", "architect", "designer",
    # Religion (other)
    "christian", "catholic", "protestant", "priest of christ",
    "bishop", "cardinal", "pope", "rabbi", "imam", "mufti",
    "shinto priest", "confucian scholar", "taoist",
    # Chinese secular
    "外交家", "政治家", "歷史學家", "历史学家", "汉学家", "漢學家",
    "东方学家", "東方學家", "考古学家", "考古學家",
    "小說家", "小说家", "詩人", "诗人", "畫家", "画家",
    "政治人物", "外交官", "部长", "部長", "总理", "總理",
]


def classify(description: str) -> tuple[bool, bool]:
    """Returns (has_buddhist, has_secular)."""
    d = description.lower()
    has_buddhist = any(kw in d for kw in BUDDHIST_KEYWORDS)
    has_secular = any(kw in d for kw in SECULAR_KEYWORDS)
    return has_buddhist, has_secular


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("Cleanup: Delete secular scholars/diplomats from persons")
    print("=" * 60)

    # Load descriptions
    with open("data/person_descriptions.json") as f:
        descs = json.load(f)
    print(f"Loaded {len(descs)} Wikidata descriptions\n")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        r = await session.execute(text("""
            SELECT id, name_zh, external_ids->>'wikidata'
            FROM kg_entities
            WHERE entity_type = 'person'
              AND (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        rows = r.fetchall()
        print(f"Scanning {len(rows)} persons...")

        to_delete = []
        secular_sample = []
        kept_buddhist = 0
        kept_unknown = 0
        no_desc = 0

        for eid, name, wid in rows:
            d = descs.get(wid, {})
            combined = f"{d.get('en','')} {d.get('zh','')}"
            if not combined.strip():
                no_desc += 1
                continue
            has_b, has_s = classify(combined)
            if has_b:
                kept_buddhist += 1
            elif has_s:
                to_delete.append(eid)
                if len(secular_sample) < 20:
                    secular_sample.append((name, combined[:80]))
            else:
                kept_unknown += 1

        print(f"\nHas Buddhist keyword (KEEP):        {kept_buddhist}")
        print(f"Secular only (DELETE):              {len(to_delete)}")
        print(f"Unknown (KEEP - no clear signal):   {kept_unknown}")
        print(f"No description (KEEP):              {no_desc}")

        print("\n=== Sample to DELETE ===")
        for name, desc in secular_sample:
            print(f"  {name}: {desc}")

        if not args.dry_run and to_delete:
            await session.execute(text("""
                DELETE FROM kg_relations WHERE subject_id=ANY(:i) OR object_id=ANY(:i)
            """), {"i": to_delete})
            batch = 200
            for i in range(0, len(to_delete), batch):
                await session.execute(text("""
                    DELETE FROM kg_entities WHERE id=ANY(:i)
                """), {"i": to_delete[i:i+batch]})
            await session.commit()
            print(f"\nDeleted {len(to_delete)} secular scholars")
        else:
            print("\nDRY RUN" if args.dry_run else "Nothing to delete")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
