"""Import Amap Buddhist temples, deduplicating against existing DB.

Filters: name must contain Buddhist keyword (寺/庵/禅/佛/精舍/丛林/讲寺).
Dedup: name_zh proximity < 2km, or amap_id match.

Input: data/amap_temples.json
"""
import argparse
import asyncio
import json
import math
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

INPUT = "data/amap_temples.json"

BUDDHIST_WORDS = ["寺", "庵", "禅", "佛", "精舍", "丛林", "讲寺", "梵"]
SKIP_WORDS = ["清真", "教堂", "基督", "天主", "道观", "道教", "伊斯兰",
              "关帝", "妈祖", "城隍", "土地庙", "孔庙", "文庙",
              "殡仪", "墓", "陵园", "酒店", "宾馆", "饭店", "餐厅",
              "停车", "公厕", "超市", "药店", "医院", "学校",
              "公园", "广场", "商场", "写字楼"]


def normalize(s: str) -> str:
    return (s or "").strip().replace(" ", "").replace("　", "")


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("FoJin — Amap Buddhist Temples Import")
    print("=" * 60)

    with open(INPUT, encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} Amap POIs")

    # Filter Buddhist only
    filtered = []
    for r in records:
        name = r.get("name", "")
        if not any(w in name for w in BUDDHIST_WORDS):
            continue
        if any(w in name for w in SKIP_WORDS):
            continue
        filtered.append(r)
    print(f"After Buddhist filter: {len(filtered)}")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        result = await session.execute(
            select(KGEntity).where(KGEntity.entity_type.in_(["place", "monastery"]))
        )
        entities = list(result.scalars().all())
        print(f"Loaded {len(entities)} existing place/monastery entities")

        by_amap: dict[str, KGEntity] = {}
        by_name: dict[str, list[KGEntity]] = {}

        for e in entities:
            ext = e.external_ids or {}
            if ext.get("amap"):
                by_amap[ext["amap"]] = e
            if e.name_zh:
                by_name.setdefault(normalize(e.name_zh), []).append(e)

        stats = {
            "matched_amap": 0,
            "matched_name_proximity": 0,
            "created": 0,
        }

        for rec in filtered:
            amap_id = rec["amap_id"]
            name = rec["name"]
            lat, lng = rec["latitude"], rec["longitude"]

            if amap_id in by_amap:
                stats["matched_amap"] += 1
                continue

            search_key = normalize(name)
            if search_key in by_name:
                matched = False
                for existing in by_name[search_key]:
                    props = existing.properties or {}
                    e_lat = props.get("latitude")
                    e_lng = props.get("longitude")
                    if e_lat is not None and e_lng is not None:
                        dist = haversine(lat, lng, float(e_lat), float(e_lng))
                        if dist < 2.0:
                            matched = True
                            break
                    else:
                        matched = True
                        break
                if matched:
                    stats["matched_name_proximity"] += 1
                    continue

            new_entity = KGEntity(
                entity_type="monastery",
                name_zh=name,
                name_en=None,
                properties={
                    "latitude": lat,
                    "longitude": lng,
                    "geo_source": "amap",
                    "country": "CN",
                    "address": rec.get("address", ""),
                    "province": rec.get("province", ""),
                    "city": rec.get("city", ""),
                    "district": rec.get("district", ""),
                },
                external_ids={"amap": amap_id},
            )
            if not args.dry_run:
                session.add(new_entity)
            stats["created"] += 1

            # Also add to by_name index to avoid duplicates within this batch
            by_name.setdefault(search_key, []).append(new_entity)

            if stats["created"] % 500 == 0:
                if not args.dry_run:
                    await session.flush()
                print(f"  ... created {stats['created']}")

        if not args.dry_run:
            await session.commit()

        print("\n" + "=" * 60)
        print("Results:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print("=" * 60)
        print(f"{'Dry run' if args.dry_run else 'Committed'}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
