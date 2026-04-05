"""Show complete data source breakdown for all geo-located Buddhist entities."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # By source family
        r = await s.execute(text("""
            SELECT
                CASE
                    WHEN properties->>'geo_source' LIKE 'osm:%' THEN 'OSM: ' || (properties->>'geo_source')
                    WHEN properties->>'geo_source' = 'bdrc' THEN 'BDRC 藏传佛教'
                    WHEN properties->>'geo_source' = 'suttacentral' THEN 'SuttaCentral 南传'
                    WHEN properties->>'geo_source' LIKE 'wikidata:中国%' THEN 'Wikidata 中国寺院'
                    WHEN properties->>'geo_source' LIKE 'wikidata:日本%' THEN 'Wikidata 日本寺院'
                    WHEN properties->>'geo_source' LIKE 'wikidata:韩国%' THEN 'Wikidata 韩国寺院'
                    WHEN properties->>'geo_source' LIKE 'wikidata:台湾%' THEN 'Wikidata 台湾寺院'
                    WHEN properties->>'geo_source' LIKE 'wikidata:越南%' THEN 'Wikidata 越南寺院'
                    WHEN properties->>'geo_source' LIKE 'wikidata:朝鲜%' THEN 'Wikidata 朝鲜寺院'
                    WHEN properties->>'geo_source' LIKE 'wikidata:theravada%' THEN 'Wikidata 南传地区'
                    WHEN properties->>'geo_source' LIKE 'wikidata:nikaya%' THEN 'Wikidata 尼柯耶地点'
                    WHEN properties->>'geo_source' LIKE 'wikidata:birth_place%'
                      OR properties->>'geo_source' LIKE 'wikidata:person%' THEN 'Wikidata 佛教人物'
                    WHEN properties->>'geo_source' LIKE 'active_in:%' THEN 'DILA active_in 传播'
                    WHEN properties->>'geo_source' LIKE 'translation_site:%' THEN 'CBETA 译场传播'
                    WHEN properties->>'geo_source' = 'wikidata:corrected' THEN 'Wikidata 坐标修正'
                    ELSE COALESCE(properties->>'geo_source', 'DILA 权威数据库(原始)')
                END as source,
                COUNT(*) as cnt
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
            GROUP BY source
            ORDER BY cnt DESC
        """))
        print("=" * 70)
        print("佛教地理 · 完整数据来源")
        print("=" * 70)
        print(f"{'来源':<50} {'数量':>10}")
        print("-" * 70)
        total = 0
        for src, cnt in r.fetchall():
            print(f"{src:<50} {cnt:>10,}")
            total += cnt
        print("-" * 70)
        print(f"{'总计':<50} {total:>10,}")

        # Breakdown by entity type
        print("\n=== 按实体类型 ===")
        r = await s.execute(text("""
            SELECT entity_type, COUNT(*)
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
            GROUP BY entity_type ORDER BY COUNT(*) DESC
        """))
        for etype, cnt in r.fetchall():
            print(f"  {etype}: {cnt:,}")

    await engine.dispose()

asyncio.run(main())
