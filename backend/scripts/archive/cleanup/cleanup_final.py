"""FINAL cleanup based on 6-agent audit."""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

NOREL = "AND NOT EXISTS (SELECT 1 FROM kg_relations r WHERE r.subject_id=e.id OR r.object_id=e.id)"
NOTBUDDHA = "AND e.name_zh NOT LIKE '%佛%' AND e.name_zh NOT LIKE '%寺%' AND e.name_zh NOT LIKE '%禅%' AND e.name_zh NOT LIKE '%庵%' AND e.name_zh NOT LIKE '%庙%' AND e.name_zh NOT LIKE '%堂%'"


async def main():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        total = 0

        deletes = [
            # === Agent 1: Random sampling finds ===
            ("Art museum/tea museum/memorial",
             "DELETE FROM kg_entities e WHERE e.id IN (44600,44610,99859) " + NOREL),

            # === Agent 2: Geographic outlier finds ===
            ("Non-Buddhist foreign (Seicho-No-Ie/watchtower/palace/etc)",
             "DELETE FROM kg_entities e WHERE e.id IN (89516,89738,89871,89368) " + NOREL),

            # === Agent 4: Cross-religion finds ===
            # Mosques disguised as 寺
            ("Mosques (清真寺 with 寺 in name)",
             "DELETE FROM kg_entities e WHERE e.id IN (91525,91531,91577,91580,91588,91589,91590,91645,91657,91659,91660,91668,91669,91701) " + NOREL),
            # Hindu temples
            ("Hindu temples",
             "DELETE FROM kg_entities e WHERE e.id IN (86759,86857,87896,88185) " + NOREL),
            # Shinto
            ("Shinto (天照教)",
             "DELETE FROM kg_entities e WHERE e.id = 69572 " + NOREL),
            # Folk religion
            ("Folk religion (百姓公/福德祠/有应公)",
             "DELETE FROM kg_entities e WHERE e.id IN (80743,80934,88194,110490) " + NOREL),
            # New religion
            ("New religion (真光教)",
             "DELETE FROM kg_entities e WHERE e.id = 81430 " + NOREL),
            # Mazu
            ("Mazu (天上聖母)",
             "DELETE FROM kg_entities e WHERE e.id = 81481 " + NOREL),
            # Vietnamese military memorial
            ("Vietnamese memorial",
             "DELETE FROM kg_entities e WHERE e.id = 83783 " + NOREL),
            # Hindu org
            ("Hindu org (Bharat Sevashram Sangha)",
             "DELETE FROM kg_entities e WHERE e.id = 89604 " + NOREL),

            # === Agent 3: Name pattern finds ===
            ("Shopping center/archives",
             "DELETE FROM kg_entities e WHERE e.id IN (44866,45254) " + NOREL),

            # === Agent 6: Amap/place/dynasty finds ===
            ("Whiskey/shrine/monument",
             "DELETE FROM kg_entities e WHERE e.id IN (43714,43799,43772) " + NOREL),
            # 分钟寺 (Beijing metro station name)
            ("分钟寺 (地名)",
             "DELETE FROM kg_entities e WHERE e.id = 91784 " + NOREL),
            # 女娲庙 (non-Buddhist)
            ("女娲庙",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND e.name_zh LIKE '%女娲%' " + NOTBUDDHA + " " + NOREL),
            # 住宅小区/度假营地
            ("住宅小区/度假营地",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND (e.name_zh LIKE '%住宅小区%' OR e.name_zh LIKE '%度假营地%') " + NOREL),

            # === Batch: Amap streets/bridges/villages ===
            ("Streets ending with 街/路/巷/弄 (Amap noise)",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND e.properties->>'geo_source' = 'amap' AND (e.name_zh ~ '街$' OR e.name_zh ~ '路$' OR e.name_zh ~ '巷$' OR e.name_zh ~ '弄$') " + NOREL),
            ("Bridges (桥)",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND e.name_zh ~ '桥$' " + NOTBUDDHA + " " + NOREL),
            ("Villages (村)",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND e.name_zh ~ '村$' " + NOTBUDDHA + " " + NOREL),
            # 林场/生态园
            ("林场/生态园/矿山",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND (e.name_zh LIKE '%林场%' OR e.name_zh LIKE '%生态园%' OR e.name_zh LIKE '%矿山%') " + NOTBUDDHA + " " + NOREL),

            # === Remaining: Guan Yu folk temples (关庙/武庙 without Buddhist terms) ===
            ("王关庙/武庙 (folk)",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND (e.name_zh LIKE '%王关庙%' OR e.name_zh LIKE '%关岳庙%') " + NOTBUDDHA + " " + NOREL),

            # ===玉皇 remaining ===
            ("玉皇 remaining",
             "DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND e.name_zh LIKE '%玉皇%' " + NOTBUDDHA + " " + NOREL),
        ]

        for label, sql in deletes:
            r = await session.execute(text(sql))
            if r.rowcount > 0:
                print(f"{label}: {r.rowcount}")
                total += r.rowcount

        # Fix dynasty 日本 -> should not be dynasty type
        r = await session.execute(text(
            "UPDATE kg_entities SET entity_type = 'place' WHERE id = 10266"
        ))
        if r.rowcount:
            print(f"Fix 日本 dynasty->place: {r.rowcount}")

        # Fix Pommaret bad coords
        r = await session.execute(text("""
            UPDATE kg_entities
            SET properties = (properties::jsonb - 'latitude' - 'longitude')::json
            WHERE id = 90104
        """))
        if r.rowcount:
            print(f"Fix Pommaret coords: {r.rowcount}")

        await session.commit()
        print(f"\nTotal deleted: {total}")

        r2 = await session.execute(text(
            "SELECT entity_type, COUNT(*) FROM kg_entities GROUP BY entity_type ORDER BY COUNT(*) DESC"
        ))
        print("\nFinal:")
        for row in r2.fetchall():
            print(f"  {row[0]}: {row[1]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
