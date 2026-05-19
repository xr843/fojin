"""Round 3 cleanup based on triple-agent audit."""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

NOREL = "AND NOT EXISTS (SELECT 1 FROM kg_relations r WHERE r.subject_id=e.id OR r.object_id=e.id)"
NOTBUDDHA = "AND e.name_zh NOT LIKE '%佛%' AND e.name_zh NOT LIKE '%寺%' AND e.name_zh NOT LIKE '%禅%' AND e.name_zh NOT LIKE '%庵%'"

DELETES = [
    ("新白马寺连锁", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%新白马寺%' OR e.name_zh LIKE '%白马寺体验%') {NOREL}"),
    ("商店", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%佛具%' OR e.name_zh LIKE '%香烛%' OR e.name_zh LIKE '%佛珠%' OR e.name_zh LIKE '%总店%' OR e.name_zh LIKE '%分店%' OR e.name_zh LIKE '%商行%' OR e.name_zh LIKE '%连锁%' OR e.name_zh LIKE '%加盟%') {NOREL}"),
    ("法物流通", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND e.name_zh LIKE '%法物流通%' {NOREL}"),
    ("萨满", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND e.name_zh LIKE '%萨满%' {NOREL}"),
    ("齐天/代天府", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%齐天大圣%' OR e.name_zh LIKE '%代天府%' OR e.name_zh LIKE '%天仙府%' OR e.name_zh LIKE '%照顯府%' OR e.name_zh LIKE '%九天府%' OR e.name_zh LIKE '%齐天府%') {NOTBUDDHA} {NOREL}"),
    ("数字人名", f"DELETE FROM kg_entities e WHERE e.entity_type = 'person' AND e.name_zh ~ '^[0-9-]+$' {NOREL}"),
    ("设施场馆", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%收费大厅%' OR e.name_zh LIKE '%盐场%' OR e.name_zh LIKE '%林场%' OR e.name_zh LIKE '%浴场%' OR e.name_zh LIKE '%修配厂%' OR e.name_zh LIKE '%汽车电器%' OR e.name_zh LIKE '%生活馆%' OR e.name_zh LIKE '%疗愈馆%' OR e.name_zh LIKE '%心灵驿站%' OR e.name_zh LIKE '%风水馆%') {NOTBUDDHA} {NOREL}"),
    ("路名街巷", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%与%交叉口%' OR e.name_zh ~ '路$' OR e.name_zh ~ '街$' OR e.name_zh ~ '巷$') {NOTBUDDHA} AND e.name_zh NOT LIKE '%庙%' AND e.name_zh NOT LIKE '%堂%' {NOREL}"),
    ("水族蜡像馆", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND (e.name_zh LIKE '%水族馆%' OR e.name_zh LIKE '%蜡像馆%' OR e.name_zh LIKE '%规划展示%' OR e.name_zh LIKE '%战犯%' OR e.name_zh LIKE '%天文馆%' OR e.name_zh LIKE '%立法院%' OR e.name_zh LIKE '%爱情乐园%' OR e.name_zh LIKE '%Seaworld%' OR e.name_zh LIKE '%Samsung%') {NOTBUDDHA} {NOREL}"),
    ("Mahikari", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND e.name_zh LIKE '%Mahikari%' {NOREL}"),
    ("会馆", f"DELETE FROM kg_entities e WHERE e.entity_type IN ('monastery','place') AND e.name_zh LIKE '%会馆%' {NOTBUDDHA} AND e.name_zh NOT LIKE '%庙%' {NOREL}"),
]


async def main():
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as session:
        total = 0
        for label, sql in DELETES:
            r = await session.execute(text(sql))
            print(f"{label}: {r.rowcount}")
            total += r.rowcount

        # Unify country: 中国 -> CN
        r = await session.execute(text("""
            UPDATE kg_entities
            SET properties = (properties::jsonb || '{"country":"CN"}'::jsonb)::json
            WHERE properties->>'country' = '中国'
        """))
        print(f"Country 中国->CN: {r.rowcount}")

        # Fix 西藏 as country -> CN
        r = await session.execute(text("""
            UPDATE kg_entities
            SET properties = (properties::jsonb || '{"country":"CN"}'::jsonb)::json
            WHERE properties->>'country' = '西藏'
        """))
        print(f"西藏->CN: {r.rowcount}")

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
