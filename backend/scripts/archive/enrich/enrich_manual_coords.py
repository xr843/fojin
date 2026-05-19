"""
Manually enrich important Buddhist sites with well-known coordinates.

These are iconic sites that must have coordinates for the map to be meaningful.
Coordinates sourced from Wikipedia/Wikidata for each site.

Usage:
    cd backend
    python -m scripts.enrich_manual_coords [--dry-run]
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

# Well-known Buddhist sites with coordinates
# Format: (name_zh, latitude, longitude, wikidata_id)
KNOWN_SITES = [
    # Indian Buddhist holy sites (八大圣地)
    ("蓝毗尼", 27.4833, 83.2833, "Q223195"),        # Lumbini — birthplace of Buddha
    ("菩提伽耶", 24.6961, 84.9911, "Q202325"),       # Bodh Gaya — enlightenment
    ("鹿野苑", 25.3814, 83.0255, "Q622644"),         # Sarnath — first sermon
    ("拘尸那揭罗", 26.7408, 83.8884, "Q585488"),     # Kushinagar — parinirvana
    ("舍卫城", 27.5131, 82.0389, "Q928691"),         # Shravasti
    ("王舍城", 25.0261, 85.4161, "Q728316"),         # Rajgir
    ("吠舍离", 25.9861, 85.1314, "Q776183"),         # Vaishali
    ("僧伽施", 27.2667, 79.6167, "Q2295406"),        # Sankassa

    # Major Indian Buddhist universities & sites
    ("那烂陀", 25.1361, 85.4428, "Q464507"),         # Nalanda
    ("超戒寺", 25.3167, 87.2833, "Q608426"),         # Vikramashila
    ("犍陀罗", 34.2333, 71.7833, "Q133220"),         # Gandhara (region)

    # Chinese Buddhist mountains (四大名山)
    ("九华山", 30.4811, 117.8021, "Q1153637"),       # Mount Jiuhua
    ("庐山", 29.5628, 115.9872, "Q211452"),          # Mount Lu
    ("终南山", 33.9500, 108.9500, "Q2023279"),       # Mount Zhongnan
    ("峨眉山", 29.5200, 103.3322, "Q309403"),        # Mount Emei
    ("普陀山", 30.0100, 122.3850, "Q2088323"),       # Mount Putuo

    # Central Asian sites on the Silk Road
    ("龟兹", 41.7178, 82.9536, "Q217568"),           # Kucha
    ("于阗", 37.1167, 79.9333, "Q248781"),           # Khotan

    # Sri Lankan sites
    ("阿努拉德普勒", 8.3114, 80.4037, "Q203541"),    # Anuradhapura

    # Tibetan sites
    ("拉萨", 29.6500, 91.1000, "Q5765"),             # Lhasa
    ("桑耶寺", 29.3289, 91.5042, "Q978802"),         # Samye Monastery

    # Japanese sites
    ("奈良", 34.6851, 135.8048, "Q167679"),          # Nara
    ("京都", 35.0116, 135.7681, "Q34600"),           # Kyoto
    ("高野山", 34.2131, 135.5833, "Q243592"),        # Mount Koya
    ("比叡山", 35.0642, 135.8381, "Q615507"),        # Mount Hiei

    # Southeast Asian sites
    ("蒲甘", 21.1717, 94.8583, "Q131746"),           # Bagan, Myanmar
    ("吴哥", 13.4125, 103.8670, "Q43473"),           # Angkor
    ("婆罗浮屠", -7.6079, 110.2038, "Q42798"),       # Borobudur

    # Korean sites
    ("庆州", 35.8561, 129.2247, "Q166862"),          # Gyeongju

    # More important Chinese locations missing coords
    ("成都", 30.5728, 104.0668, "Q30002"),           # Chengdu
    ("杭州", 30.2741, 120.1551, "Q4970"),            # Hangzhou
    ("广州", 23.1291, 113.2644, "Q16572"),           # Guangzhou
    ("太原", 37.8706, 112.5489, "Q72778"),           # Taiyuan
    ("开封", 34.7972, 114.3078, "Q189869"),          # Kaifeng
    ("凉州", 37.9283, 102.6417, "Q1093085"),         # Liangzhou (already may exist)
]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 (FoJin) — Manual Coordinate Enrichment")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN\n")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        updated = 0
        not_found = 0

        for name_zh, lat, lng, wikidata_id in KNOWN_SITES:
            # Find entity by Chinese name
            result = await session.execute(
                select(KGEntity).where(KGEntity.name_zh == name_zh)
            )
            entity = result.scalar_one_or_none()

            if not entity:
                # Also try traditional/simplified variants
                not_found += 1
                print(f"  ? {name_zh} — not found in KG")
                continue

            props = dict(entity.properties or {})
            if props.get("latitude") and props.get("longitude"):
                print(f"  = {name_zh} — already has coords ({props['latitude']}, {props['longitude']})")
                continue

            props["latitude"] = lat
            props["longitude"] = lng

            ext_ids = dict(entity.external_ids or {})
            if not ext_ids.get("wikidata"):
                ext_ids["wikidata"] = wikidata_id
                entity.external_ids = ext_ids

            if not args.dry_run:
                entity.properties = props

            updated += 1
            print(f"  + {name_zh} ({entity.entity_type}) ← ({lat}, {lng}) [{wikidata_id}]")

        if not args.dry_run and updated > 0:
            await session.commit()
            print(f"\nCommitted {updated} updates.")
        else:
            print(f"\n{'Dry run' if args.dry_run else 'No updates needed'}.")

        print(f"\nSummary: {updated} updated, {not_found} not found in KG")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
