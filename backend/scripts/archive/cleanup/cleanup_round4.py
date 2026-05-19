"""Round 4 cleanup: Middle East noise, whiskey brands, Amap deep scan."""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

NOREL = "AND NOT EXISTS (SELECT 1 FROM kg_relations r WHERE r.subject_id=e.id OR r.object_id=e.id)"
NOTBUDDHA = "AND e.name_zh NOT LIKE '%佛%' AND e.name_zh NOT LIKE '%寺%' AND e.name_zh NOT LIKE '%禅%' AND e.name_zh NOT LIKE '%庵%' AND e.name_zh NOT LIKE '%庙%'"


async def main():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        total = 0

        deletes = [
            # Specific IDs: whiskey brands, Hindu temple, Christian monk
            ("Whiskey/Hindu/Christian",
             "DELETE FROM kg_entities e WHERE e.id IN (43507,43509,43518,43583,43634,43664,43705,43706,43710,43727,43739,88275,52165)"),

            # Fix bad coordinates for Françoise Pommaret
            ("Fix Pommaret coords",
             "UPDATE kg_entities SET properties = properties::jsonb - 'latitude' - 'longitude' WHERE id = 90104"),

            # Amap noise: 养生/保健/理疗/足浴/按摩/美容
            (f"养生保健", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%养生%' OR e.name_zh LIKE '%保健%' OR e.name_zh LIKE '%理疗%' OR e.name_zh LIKE '%足浴%' OR e.name_zh LIKE '%按摩%' OR e.name_zh LIKE '%美容%' OR e.name_zh LIKE '%健身%') {NOTBUDDHA} {NOREL}"),

            # 殡葬/寿衣/花圈/骨灰
            (f"殡葬", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%殡葬%' OR e.name_zh LIKE '%寿衣%' OR e.name_zh LIKE '%花圈%' OR e.name_zh LIKE '%骨灰%') {NOTBUDDHA} {NOREL}"),

            # 棋牌/麻将/网吧/KTV/酒吧
            (f"娱乐", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%棋牌%' OR e.name_zh LIKE '%麻将%' OR e.name_zh LIKE '%网吧%' OR e.name_zh LIKE '%KTV%' OR e.name_zh LIKE '%酒吧%' OR e.name_zh LIKE '%歌厅%') {NOREL}"),

            # 出租/搬家/家政/装修/维修
            (f"服务业", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%出租%' OR e.name_zh LIKE '%搬家%' OR e.name_zh LIKE '%家政%' OR e.name_zh LIKE '%装修%' OR e.name_zh LIKE '%维修%') {NOTBUDDHA} {NOREL}"),

            # 旅行社/旅游公司
            (f"旅行社", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%旅行社%' OR e.name_zh LIKE '%旅游公司%') {NOREL}"),

            # (暂停营业)/(已关闭)
            (f"已关闭", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%(暂停营业)%' OR e.name_zh LIKE '%(已关闭)%' OR e.name_zh LIKE '%(搬迁)%') {NOREL}"),

            # 太仆寺旗XX (行政区名非寺院)
            (f"太仆寺旗", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND e.name_zh LIKE '%太仆寺旗%' AND e.name_zh NOT LIKE '%太仆寺旗寺%' {NOREL}"),

            # 佛堂镇XX (义乌佛堂镇地名)
            (f"佛堂镇", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND e.name_zh LIKE '%佛堂镇%' {NOREL}"),

            # Names ending with 村/组/屯/营/寨 (without Buddhist terms)
            (f"村寨地名", f"DELETE FROM kg_entities e WHERE e.entity_type = 'monastery' AND (e.name_zh ~ '村$' OR e.name_zh ~ '组$' OR e.name_zh ~ '屯$') {NOTBUDDHA} AND e.name_zh NOT LIKE '%堂%' {NOREL}"),

            # 幼儿园/培训
            (f"教育", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%幼儿园%' OR e.name_zh LIKE '%培训%') {NOTBUDDHA} {NOREL}"),

            # 残留纪念馆/档案馆
            (f"纪念馆", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%纪念馆%' OR e.name_zh LIKE '%档案馆%' OR e.name_zh LIKE '%文物馆%' OR e.name_zh LIKE '%艺术馆%') {NOTBUDDHA} {NOREL}"),
        ]

        for label, sql in deletes:
            r = await session.execute(text(sql))
            cnt = r.rowcount
            if cnt > 0:
                print(f"{label}: {cnt}")
            total += cnt

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
