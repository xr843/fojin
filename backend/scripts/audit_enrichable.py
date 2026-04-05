"""Count how many non-Chinese entities have Wikidata Q-IDs (enrichable)."""
import asyncio, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

CJK = re.compile(r'[\u4E00-\u9FFF]')

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT external_ids->>'wikidata' as wid, name_zh,
                   description IS NOT NULL as has_desc
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        rows = r.fetchall()

        non_zh_with_wd = 0
        no_desc_with_wd = 0
        both = 0
        for wid, name_zh, has_desc in rows:
            is_zh = bool(CJK.search(name_zh or ""))
            if not is_zh:
                non_zh_with_wd += 1
            if not has_desc:
                no_desc_with_wd += 1
            if not is_zh and not has_desc:
                both += 1

        print(f"有 Wikidata Q-ID 的实体: {len(rows)}")
        print(f"名称非中文且有 Q-ID (可补中文名): {non_zh_with_wd}")
        print(f"无描述且有 Q-ID (可补描述): {no_desc_with_wd}")
        print(f"两者皆缺可补: {both}")

    await engine.dispose()

asyncio.run(main())
