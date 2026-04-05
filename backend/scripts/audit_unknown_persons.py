"""Review the 'unknown' persons — those with descriptions that have no
clear Buddhist OR secular signal. Print sample for user review."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# From cleanup_secular_scholars.py
BUDDHIST_KEYWORDS = [
    "buddhist", "buddhism", "佛教", "佛学", "佛陀",
    "monk", "nun", " bhikkhu", " bhikkhuni", "sramana",
    "僧", "和尚", "法師", "法师", "禪師", "禅师", "禪宗", "禅宗",
    "喇嘛", "活佛", "仁波切", "比丘", "比丘尼", "法王",
    "祖师", "祖師", "高僧", "大师", "尊者", "上人",
    "chan master", "zen master", "zen buddhism", "chan buddhism",
    "tibetan buddhist", "vajrayana", "theravada", "mahayana",
    "pure land", "净土", "淨土", "天台", "华严", "華嚴",
    "唯识", "唯識", "律宗", "密宗",
    "dalai lama", "panchen", "karmapa", "rinpoche", "tulku", "lama",
    "班禅", "达赖", "噶玛巴",
    "arhat", "bodhisattva", "dharma ", "sangha", "sutra", "tripitaka",
    "菩薩", "菩萨", "羅漢", "罗汉",
]
SECULAR_KEYWORDS = [
    "historian", "orientalist", "sinologist", "indologist", "tibetologist",
    "diplomat", "ambassador", "statesman", "politician", "minister",
    "general ", "admiral ", "military officer",
    "jurist", "lawyer", "businessman",
    "biologist", "naturalist", "physicist", "chemist", "engineer",
    "painter", "novelist", "playwright", "musician", "composer",
    "christian", "catholic", "protestant", "bishop", "cardinal", "pope",
    "外交家", "政治家", "歷史學家", "历史学家", "汉学家", "漢學家",
    "政治人物", "外交官", "部长", "部長",
]

async def main():
    with open("data/person_descriptions.json") as f:
        descs = json.load(f)

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT id, name_zh, external_ids->>'wikidata'
            FROM kg_entities
            WHERE entity_type='person' AND (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        rows = r.fetchall()

        unknowns = []
        for eid, name, wid in rows:
            d = descs.get(wid, {})
            combined = f"{d.get('en','')} {d.get('zh','')}".lower()
            if not combined.strip():
                continue
            has_b = any(k in combined for k in BUDDHIST_KEYWORDS)
            has_s = any(k in combined for k in SECULAR_KEYWORDS)
            if not has_b and not has_s:
                unknowns.append((eid, name, combined))

        print(f"Unknown count: {len(unknowns)}")
        print("\n=== Sample of 'unknown' persons ===")
        import random
        random.seed(42)
        sample = random.sample(unknowns, min(60, len(unknowns)))
        for eid, name, desc in sample:
            print(f"  #{eid} {name}: {desc[:100]}")

    await engine.dispose()

asyncio.run(main())
