"""Enrich entity name_zh + description from Wikidata batch lookup."""
import argparse
import asyncio
import json
import os
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

INPUT = "data/wikidata_zh_labels.json"
CJK = re.compile(r'[\u4E00-\u9FFF]')


def is_chinese(s: str) -> bool:
    return bool(s and CJK.search(s))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(INPUT, encoding="utf-8") as f:
        wd_data = json.load(f)
    print(f"Loaded {len(wd_data)} Wikidata labels")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {
        "label_updated": 0,
        "desc_zh_added": 0,
        "desc_en_added": 0,
        "label_en_added": 0,
        "skipped_no_match": 0,
    }

    async with sf() as session:
        r = await session.execute(text("""
            SELECT id, name_zh, name_en, description, external_ids->>'wikidata'
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        rows = r.fetchall()
        print(f"Scanning {len(rows)} entities with Q-IDs")

        for eid, name_zh, name_en, desc, wid in rows:
            wd = wd_data.get(wid)
            if not wd:
                stats["skipped_no_match"] += 1
                continue

            updated = False
            label_zh = wd.get("label_zh")
            label_en = wd.get("label_en")
            desc_zh = wd.get("desc_zh")
            desc_en = wd.get("desc_en")

            # Replace name_zh if currently non-Chinese and Wikidata has Chinese
            if label_zh and is_chinese(label_zh) and not is_chinese(name_zh):
                if not args.dry_run:
                    await session.execute(text("""
                        UPDATE kg_entities SET name_zh = :n WHERE id = :id
                    """), {"n": label_zh, "id": eid})
                stats["label_updated"] += 1
                updated = True

            # Add name_en if missing
            if label_en and not name_en:
                if not args.dry_run:
                    await session.execute(text("""
                        UPDATE kg_entities SET name_en = :n WHERE id = :id
                    """), {"n": label_en, "id": eid})
                stats["label_en_added"] += 1

            # Add description (prefer zh, fallback to en)
            if not desc:
                new_desc = desc_zh or desc_en
                if new_desc:
                    if not args.dry_run:
                        await session.execute(text("""
                            UPDATE kg_entities SET description = :d WHERE id = :id
                        """), {"d": new_desc, "id": eid})
                    if desc_zh:
                        stats["desc_zh_added"] += 1
                    else:
                        stats["desc_en_added"] += 1

        if not args.dry_run:
            await session.commit()

        print("\nResults:")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
