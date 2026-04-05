"""Detailed audit of person entities with coords - find secular scholars."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # Load descriptions we fetched earlier
        descs = {}
        try:
            with open("data/person_descriptions.json") as f:
                descs = json.load(f)
        except Exception:
            print("No descriptions file yet")

        # Get all persons with coords from wikidata
        r = await s.execute(text("""
            SELECT id, name_zh, external_ids->>'wikidata' as wid, properties->>'geo_source' as src
            FROM kg_entities
            WHERE entity_type = 'person'
              AND (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
            ORDER BY id
        """))
        rows = r.fetchall()
        print(f"Total wikidata persons with coords: {len(rows)}")

        # Classify by description
        clergy_kws = [
            "buddhist monk", "buddhist nun", "buddhist priest", "buddhist teacher",
            "buddhist master", "buddhist philosopher", "buddhist scholar",
            "chan master", "zen master", "zen monk", "dalai lama", "panchen lama",
            "rinpoche", "tulku", "lama", "bhikkhu", "bhikkhuni", "arhat",
            "僧", "和尚", "法师", "禅师", "禪師", "高僧", "祖师", "大师", "佛教徒",
            "上人", "活佛", "喇嘛", "仁波切", "比丘", "比丘尼", "菩萨", "禅宗",
            "禪宗", "天台宗", "净土宗", "律宗", "华严宗", "唯识宗",
            "patriarch of", "founder of",
        ]
        scholar_only_kws = [
            "indologist", "tibetologist", "buddhologist", "sinologist",
            "scholar of", "researcher", "professor of", "academic",
            "university teacher", "university professor", "historian",
            "orientalist", "philologist",
            "研究员", "研究員", "学者", "學者", "教授",
        ]

        buddhist_count = 0
        scholar_count = 0
        no_desc = 0
        unknown = 0
        scholars_to_show = []
        unknowns_to_show = []

        for row in rows:
            eid, name, wid, src = row
            d = descs.get(wid, {})
            combined = f"{d.get('en','')} {d.get('zh','')}".lower()

            if not combined.strip():
                no_desc += 1
                continue

            is_clergy = any(kw in combined for kw in clergy_kws)
            is_scholar = any(kw in combined for kw in scholar_only_kws)

            if is_clergy:
                buddhist_count += 1
            elif is_scholar:
                scholar_count += 1
                if len(scholars_to_show) < 30:
                    scholars_to_show.append((eid, name, wid, combined[:100]))
            else:
                unknown += 1
                if len(unknowns_to_show) < 30:
                    unknowns_to_show.append((eid, name, wid, combined[:100]))

        print(f"\nBreakdown:")
        print(f"  佛教人物 (clergy): {buddhist_count}")
        print(f"  学者/研究员 (secular scholars): {scholar_count}")
        print(f"  无佛教也无学者 (unknown): {unknown}")
        print(f"  无描述: {no_desc}")

        print("\n=== Secular scholars to REMOVE ===")
        for eid, name, wid, d in scholars_to_show:
            print(f"  #{eid} {name} [{wid}]: {d}")

        print("\n=== Unknown (need review) ===")
        for eid, name, wid, d in unknowns_to_show:
            print(f"  #{eid} {name} [{wid}]: {d}")

    await engine.dispose()

asyncio.run(main())
