"""Audit geo-coordinate entities for non-Buddhist noise."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

NOISE_KEYWORDS = [
    "博物馆", "博物館", "museum", "纪念馆", "紀念館",
    "文物馆", "文物館", "memorial hall", "memorial museum",
    "exhibition", "展览馆", "展覽館", "archive", "archives", "档案馆",
    "research center", "研究中心", "university", "大学", "college",
    "历史博物馆", "历史公园", "historical park", "monument",
    "石刻", "石碑", "纪念碑", "memorial", "纪念塔", "cemetery", "公墓",
    "park", "公园", "公園", "国家公园", "garden", "花园",
]

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # Find potential noise entities
        print("=== 潜在噪音实体 (名称含博物馆/纪念馆/公园等) ===\n")
        total_noise = 0
        for kw in NOISE_KEYWORDS:
            r = await s.execute(text("""
                SELECT COUNT(*) FROM kg_entities
                WHERE (properties->>'latitude') IS NOT NULL
                  AND entity_type IN ('monastery', 'place', 'person')
                  AND (name_zh ILIKE :kw OR name_en ILIKE :kw)
            """), {"kw": f"%{kw}%"})
            cnt = r.scalar()
            if cnt > 0:
                print(f"  {kw}: {cnt}")
                total_noise += cnt

        # Sample actual noise entries
        print("\n=== 样本: 名称含 '博物馆' 的实体 ===")
        r = await s.execute(text("""
            SELECT name_zh, name_en, entity_type, external_ids
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (name_zh ILIKE '%博物馆%' OR name_zh ILIKE '%博物館%'
                OR name_en ILIKE '%museum%')
            LIMIT 20
        """))
        for row in r.fetchall():
            print(f"  [{row[2]}] {row[0]} | {row[1]} | {row[3]}")

        print("\n=== 样本: 名称含 'park/memorial' 的实体 ===")
        r = await s.execute(text("""
            SELECT name_zh, name_en, entity_type, external_ids
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND (name_en ILIKE '%park%' OR name_en ILIKE '%memorial%'
                OR name_zh ILIKE '%公园%' OR name_zh ILIKE '%纪念%')
            LIMIT 20
        """))
        for row in r.fetchall():
            print(f"  [{row[2]}] {row[0]} | {row[1]} | {row[3]}")

        # Check by source
        print("\n=== 按来源分组 ===")
        r = await s.execute(text("""
            SELECT
                CASE
                    WHEN properties->>'geo_source' LIKE 'wikidata:中国%' THEN 'wikidata:中国'
                    WHEN properties->>'geo_source' LIKE 'wikidata:日本%' THEN 'wikidata:日本'
                    WHEN properties->>'geo_source' LIKE 'wikidata:韩国%' THEN 'wikidata:韩国'
                    WHEN properties->>'geo_source' LIKE 'wikidata:台湾%' THEN 'wikidata:台湾'
                    WHEN properties->>'geo_source' LIKE 'wikidata:越南%' THEN 'wikidata:越南'
                    WHEN properties->>'geo_source' LIKE 'wikidata:朝鲜%' THEN 'wikidata:朝鲜'
                    WHEN properties->>'geo_source' = 'bdrc' THEN 'bdrc'
                    WHEN properties->>'geo_source' = 'suttacentral' THEN 'suttacentral'
                    WHEN properties->>'geo_source' LIKE 'wikidata:birth_place%' THEN 'wikidata:person'
                    WHEN properties->>'geo_source' LIKE 'wikidata:person%' THEN 'wikidata:person'
                    WHEN properties->>'geo_source' LIKE 'active_in:%' THEN 'active_in'
                    WHEN properties->>'geo_source' LIKE 'translation_site:%' THEN 'translation_site'
                    ELSE COALESCE(properties->>'geo_source', 'DILA(original)')
                END as src,
                COUNT(*)
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
            GROUP BY src ORDER BY COUNT(*) DESC
        """))
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}")

        print(f"\n总噪音匹配: {total_noise} (可能有重复计算)")

    await engine.dispose()

asyncio.run(main())
