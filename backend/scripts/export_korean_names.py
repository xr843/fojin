"""Export unique Korean hangul entity names for offline hanja lookup."""
import asyncio, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

HANGUL = re.compile(r'[\uAC00-\uD7AF]')
CJK = re.compile(r'[\u4E00-\u9FFF]')

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT DISTINCT name_zh FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
        """))
        names = [row[0] for row in r.fetchall()]
    await engine.dispose()

    # Filter hangul-only names
    korean = sorted(set(n for n in names if n and HANGUL.search(n) and not CJK.search(n)))
    with open("/data/korean_hangul_names.json", "w", encoding="utf-8") as f:
        json.dump(korean, f, ensure_ascii=False)
    print(f"Exported {len(korean)} Korean hangul names")

asyncio.run(main())
