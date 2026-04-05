"""Audit remaining wikidata-sourced entities for non-Buddhist content."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# Sample entities that do NOT contain Buddhist keywords
# These are likely noise still in the DB
async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # Non-Buddhist keyword patterns
        suspects = [
            "城堡", "castle", "皇宫", "palace", "王宫",
            "酒店", "hotel", "宾馆",
            "商场", "mall", "购物",
            "school", "学校",
            "hospital", "医院",
            "airport", "机场",
            "station", "站",
            "mosque", "清真寺",
            "church", "教堂", "大教堂",
            "cathedral",
            "synagogue", "犹太",
            "平台", "plaza",
            "factory", "工厂",
            "观光塔", "观景台", "lookout",
            "farm", "农场",
            "theater", "剧院", "劇院",
            "cinema", "电影院",
            "market", "市场",
            "bar ", "pub",
            "restaurant", "餐厅",
            "garage", "parking",
            "office", "办公",
            "headquarters",
            "embassy", "使馆",
        ]

        for pat in suspects:
            r = await s.execute(text("""
                SELECT COUNT(*) FROM kg_entities
                WHERE (properties->>'latitude') IS NOT NULL
                  AND (properties->>'geo_source' LIKE 'wikidata:%' OR properties->>'geo_source' = 'bdrc')
                  AND (name_zh ILIKE :pat OR name_en ILIKE :pat)
            """), {"pat": f"%{pat}%"})
            cnt = r.scalar()
            if cnt > 0:
                print(f"{pat}: {cnt}")
                r2 = await s.execute(text("""
                    SELECT name_zh, name_en FROM kg_entities
                    WHERE (properties->>'latitude') IS NOT NULL
                      AND (properties->>'geo_source' LIKE 'wikidata:%' OR properties->>'geo_source' = 'bdrc')
                      AND (name_zh ILIKE :pat OR name_en ILIKE :pat)
                    LIMIT 5
                """), {"pat": f"%{pat}%"})
                for row in r2.fetchall():
                    print(f"  - {row[0]} | {row[1]}")

        # Check persons too — Persons mis-categorized as celebrities/politicians
        print("\n=== Person entities with no Buddhist keywords ===")
        r = await s.execute(text("""
            SELECT name_zh, name_en, description FROM kg_entities
            WHERE entity_type = 'person'
              AND (properties->>'latitude') IS NOT NULL
              AND properties->>'geo_source' LIKE 'wikidata:%'
              AND (name_zh NOT LIKE '%佛%' AND name_zh NOT LIKE '%僧%'
                AND name_zh NOT LIKE '%法%' AND name_zh NOT LIKE '%禅%'
                AND name_zh NOT LIKE '%禪%' AND name_zh NOT LIKE '%尊%'
                AND name_zh NOT LIKE '%和尚%' AND name_zh NOT LIKE '%喇嘛%'
                AND name_zh NOT LIKE '%仁波切%' AND name_zh NOT LIKE '%活佛%'
                AND name_zh NOT LIKE '%菩萨%' AND name_zh NOT LIKE '%羅漢%')
            LIMIT 15
        """))
        for row in r.fetchall():
            print(f"  {row[0]} | {row[1]}")

    await engine.dispose()

asyncio.run(main())
