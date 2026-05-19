"""
Assign proxy coordinates to persons based on their dynasty.

Each dynasty's scholars/monks were primarily active around the capital city.
This uses the dynasty capital as a proxy coordinate with slight random offset
to avoid all dots stacking on the same point.

Usage:
    cd backend
    python -m scripts.enrich_dynasty_coords [--dry-run]
"""
import argparse
import asyncio
import os
import random
import sys

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

# Dynasty → capital city coordinates + year range
# Format: dynasty_name → (latitude, longitude, year_start, year_end)
DYNASTY_CAPITALS: dict[str, tuple[float, float, int, int]] = {
    # Chinese dynasties
    "東漢": (34.72, 112.62, 25, 220),           # Luoyang
    "三國": (34.33, 108.91, 220, 280),           # Chang'an / various
    "西晉": (34.72, 112.62, 266, 316),           # Luoyang
    "東晉": (32.06, 118.78, 317, 420),           # Jiankang (Nanjing)
    "十六國": (34.33, 108.91, 304, 439),          # Various
    "南朝": (32.06, 118.78, 420, 589),            # Jiankang
    "北朝": (34.72, 112.62, 386, 581),            # Luoyang / various
    "隋": (34.33, 108.91, 581, 618),              # Chang'an
    "唐": (34.33, 108.91, 618, 907),              # Chang'an
    "五代十國": (34.80, 114.31, 907, 979),        # Kaifeng / various
    "北宋": (34.80, 114.31, 960, 1127),           # Kaifeng
    "南宋": (30.27, 120.16, 1127, 1279),          # Hangzhou
    "宋": (34.80, 114.31, 960, 1279),             # Kaifeng (generic Song)
    "遼": (39.91, 116.40, 916, 1125),             # various
    "金": (39.91, 116.40, 1115, 1234),            # Zhongdu (Beijing)
    "元": (39.91, 116.40, 1271, 1368),            # Dadu (Beijing)
    "明": (39.91, 116.40, 1368, 1644),            # Beijing
    "清": (39.91, 116.40, 1644, 1912),            # Beijing
    "民國": (32.06, 118.78, 1912, 1949),          # Nanjing

    # Multi-dynasty (use later one)
    "明\n    清": (39.91, 116.40, 1368, 1912),
    "元\n    明": (39.91, 116.40, 1271, 1644),
    "清\n    民國": (39.91, 116.40, 1644, 1949),
    "隋\n    唐": (34.33, 108.91, 581, 907),
    "唐\n    五代十國": (34.33, 108.91, 618, 979),

    # Japanese periods
    "日本": (34.69, 135.50, 600, 1900),           # Kyoto/Nara region
    "奈良時代": (34.69, 135.81, 710, 794),        # Nara
    "平安時代": (35.01, 135.77, 794, 1185),       # Kyoto
    "鎌倉時代": (35.32, 139.55, 1185, 1333),      # Kamakura
    "室町時代": (35.01, 135.77, 1336, 1573),       # Kyoto
    "江戶時代": (35.68, 139.77, 1603, 1868),       # Edo (Tokyo)

    # Korean periods
    "朝鮮": (37.57, 126.98, 1392, 1897),          # Seoul (Hanyang)
    "高麗": (37.97, 126.56, 918, 1392),            # Kaesong
    "新羅": (35.86, 129.22, 57, 935),              # Gyeongju
    "百濟": (36.48, 126.93, -18, 660),             # Gongju/Buyeo
}

# Spread radius in degrees (~30km at equator) to avoid stacking
SPREAD = 0.4


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 (FoJin) — Dynasty-based Coordinate Assignment")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN\n")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    random.seed(42)  # Reproducible spread

    async with sf() as session:
        total_updated = 0

        for dynasty, (lat, lng, year_start, year_end) in DYNASTY_CAPITALS.items():
            # Find persons of this dynasty without coordinates
            # Handle newlines in dynasty names (multi-dynasty)
            dynasty_clean = dynasty.replace("\n    ", "\n")
            r = await session.execute(text("""
                SELECT id FROM kg_entities
                WHERE entity_type = 'person'
                  AND (properties->>'latitude') IS NULL
                  AND properties->>'dynasty' = :dynasty
            """), {"dynasty": dynasty_clean})
            ids = [row[0] for row in r.fetchall()]

            if not ids:
                continue

            count = 0
            for eid in ids:
                offset_lat = (random.random() - 0.5) * SPREAD * 2
                offset_lng = (random.random() - 0.5) * SPREAD * 2

                if not args.dry_run:
                    entity = await session.get(KGEntity, eid)
                    if not entity:
                        continue
                    props = dict(entity.properties or {})
                    props["latitude"] = lat + offset_lat
                    props["longitude"] = lng + offset_lng
                    props["year_start"] = year_start
                    props["year_end"] = year_end
                    props["geo_source"] = f"dynasty:{dynasty_clean}"
                    entity.properties = props

                count += 1

                if count % 200 == 0:
                    await session.flush()

            total_updated += count
            print(f"  {dynasty.replace(chr(10), '/')}: {count} persons → ({lat}, {lng})")

        if not args.dry_run:
            await session.commit()

        print(f"\nTotal: {total_updated} persons assigned coordinates")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
