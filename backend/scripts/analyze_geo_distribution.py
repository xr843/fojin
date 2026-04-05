"""Analyze geographic data distribution and identify gaps."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # 1. Geo source breakdown
        r = await s.execute(text("""
            SELECT properties->>'geo_source' as src, COUNT(*)
            FROM kg_entities WHERE (properties->>'latitude') IS NOT NULL
            GROUP BY src ORDER BY COUNT(*) DESC
        """))
        print("=== 坐标来源分布 ===")
        for row in r.fetchall():
            print(f"  {row[0] or '(原始DILA数据)'}: {row[1]}")

        # 2. Geographic clusters (round to 1 decimal)
        r = await s.execute(text("""
            SELECT
                ROUND((properties->>'latitude')::numeric, 0) as lat_r,
                ROUND((properties->>'longitude')::numeric, 0) as lng_r,
                COUNT(*) as cnt
            FROM kg_entities WHERE (properties->>'latitude') IS NOT NULL
            GROUP BY lat_r, lng_r
            ORDER BY cnt DESC LIMIT 15
        """))
        print("\n=== 地理聚类（Top 15 密集区域）===")
        for row in r.fetchall():
            print(f"  ({row[0]}, {row[1]}): {row[2]} entities")

        # 3. Persons WITHOUT coords and WITHOUT dynasty
        r = await s.execute(text("""
            SELECT COUNT(*) FROM kg_entities
            WHERE entity_type='person'
              AND (properties->>'latitude') IS NULL
              AND (properties->>'dynasty' IS NULL OR properties->>'dynasty' = '')
        """))
        print(f"\n无坐标且无朝代的人物: {r.scalar()}")

        # 4. Persons with dynasty that didn't get mapped
        r = await s.execute(text("""
            SELECT properties->>'dynasty', COUNT(*)
            FROM kg_entities
            WHERE entity_type='person'
              AND (properties->>'latitude') IS NULL
              AND properties->>'dynasty' IS NOT NULL
            GROUP BY properties->>'dynasty'
            ORDER BY COUNT(*) DESC LIMIT 10
        """))
        print("\n=== 有朝代但仍无坐标的人物 ===")
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}")

        # 5. Indian/South Asian entities
        r = await s.execute(text("""
            SELECT name_zh, entity_type,
                   (properties->>'latitude')::float as lat,
                   (properties->>'longitude')::float as lng
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (properties->>'latitude')::float BETWEEN 5 AND 35
              AND (properties->>'longitude')::float BETWEEN 68 AND 100
            ORDER BY entity_type, name_zh
        """))
        rows = r.fetchall()
        print(f"\n=== 南亚/印度区域实体 ({len(rows)}) ===")
        for row in rows:
            print(f"  [{row[1]}] {row[0]} ({row[2]:.2f}, {row[3]:.2f})")

        # 6. Central Asia / Silk Road
        r = await s.execute(text("""
            SELECT name_zh, entity_type,
                   (properties->>'latitude')::float as lat,
                   (properties->>'longitude')::float as lng
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (properties->>'latitude')::float BETWEEN 30 AND 45
              AND (properties->>'longitude')::float BETWEEN 60 AND 90
            ORDER BY name_zh
        """))
        rows = r.fetchall()
        print(f"\n=== 中亚/西域区域实体 ({len(rows)}) ===")
        for row in rows:
            print(f"  [{row[1]}] {row[0]} ({row[2]:.2f}, {row[3]:.2f})")

        # 7. Southeast Asia
        r = await s.execute(text("""
            SELECT COUNT(*) FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (properties->>'latitude')::float BETWEEN -10 AND 20
              AND (properties->>'longitude')::float BETWEEN 90 AND 140
        """))
        print(f"\n东南亚区域实体: {r.scalar()}")

        # 8. active_in relation targets analysis
        r = await s.execute(text("""
            SELECT pl.name_zh, pl.name_en, COUNT(r.id) as person_count,
                   (pl.properties->>'latitude') IS NOT NULL as has_coord
            FROM kg_relations r
            JOIN kg_entities pl ON pl.id = r.object_id
            WHERE r.predicate = 'active_in'
            GROUP BY pl.id, pl.name_zh, pl.name_en, has_coord
            ORDER BY person_count DESC LIMIT 20
        """))
        print("\n=== active_in 关系目标地点 Top 20 ===")
        for row in r.fetchall():
            status = "✓" if row[3] else "✗"
            print(f"  {status} {row[0]} ({row[1] or '-'}): {row[2]} persons")

    await engine.dispose()

asyncio.run(main())
