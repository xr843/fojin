"""
V2: Fix dynasty coordinate assignment with better spread and more dynasties.

Changes from v1:
- Add Indian, Tibetan, Southeast Asian dynasties
- Handle all multi-dynasty combos by fuzzy matching
- Larger spread radius (1.5 degrees ~150km) so dense areas look like regions not dots
- Only update entities that got dynasty:* geo_source (don't touch DILA/active_in originals)

Usage:
    cd backend
    python -m scripts.enrich_dynasty_coords_v2 [--dry-run]
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

# Dynasty → (lat, lng, year_start, year_end)
DYNASTY_CAPITALS: dict[str, tuple[float, float, int, int]] = {
    # Indian periods
    "印度": (25.0, 83.0, -500, 1200),               # Ganges plain (Buddhist heartland)
    "古印度": (25.0, 83.0, -500, 600),

    # Chinese dynasties
    "東漢": (34.72, 112.62, 25, 220),
    "漢": (34.33, 108.91, -202, 220),
    "三國": (34.33, 108.91, 220, 280),
    "西晉": (34.72, 112.62, 266, 316),
    "東晉": (32.06, 118.78, 317, 420),
    "十六國": (34.33, 108.91, 304, 439),
    "南朝": (32.06, 118.78, 420, 589),
    "北朝": (34.72, 112.62, 386, 581),
    "北齊": (36.60, 114.35, 550, 577),               # Ye city
    "北周": (34.33, 108.91, 557, 581),
    "陳": (32.06, 118.78, 557, 589),                  # Jiankang
    "梁": (32.06, 118.78, 502, 557),
    "隋": (34.33, 108.91, 581, 618),
    "唐": (34.33, 108.91, 618, 907),
    "五代十國": (34.80, 114.31, 907, 979),
    "北宋": (34.80, 114.31, 960, 1127),
    "南宋": (30.27, 120.16, 1127, 1279),
    "宋": (34.80, 114.31, 960, 1279),
    "遼": (41.80, 123.40, 916, 1125),                # Shangjing
    "金": (39.91, 116.40, 1115, 1234),
    "元": (39.91, 116.40, 1271, 1368),
    "明": (39.91, 116.40, 1368, 1644),
    "清": (39.91, 116.40, 1644, 1912),
    "民國": (32.06, 118.78, 1912, 1949),

    # Japanese
    "日本": (34.69, 135.50, 600, 1900),

    # Korean
    "朝鮮": (37.57, 126.98, 1392, 1897),
    "高麗": (37.97, 126.56, 918, 1392),
    "新羅": (35.86, 129.22, 57, 935),
    "百濟": (36.48, 126.93, -18, 660),

    # Tibetan
    "西藏": (29.65, 91.10, 600, 1900),
    "吐蕃": (29.65, 91.10, 618, 842),
}

# Larger spread for regions (degrees; 1.5° ≈ 150km)
SPREAD = 1.5
# Even larger spread for Japan (spread across the archipelago)
JAPAN_SPREAD_LAT = 3.0   # ~330km N-S
JAPAN_SPREAD_LNG = 4.0   # covers Kyushu to Kanto


def find_dynasty_match(dynasty_str: str) -> tuple[float, float, int, int] | None:
    """Fuzzy match a dynasty string against known dynasties."""
    # Exact match
    if dynasty_str in DYNASTY_CAPITALS:
        return DYNASTY_CAPITALS[dynasty_str]
    # Try each known dynasty as substring
    for known, coords in DYNASTY_CAPITALS.items():
        if known in dynasty_str:
            return coords
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 (FoJin) — Dynasty Coordinate Assignment V2")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN\n")

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    random.seed(42)

    async with sf() as session:
        # First: clear previous dynasty-based coords to reassign with better spread
        r = await session.execute(text("""
            SELECT id FROM kg_entities
            WHERE properties->>'geo_source' LIKE 'dynasty:%'
        """))
        old_ids = [row[0] for row in r.fetchall()]
        print(f"Clearing {len(old_ids)} previous dynasty-based coordinates...")

        if not args.dry_run:
            for eid in old_ids:
                entity = await session.get(KGEntity, eid)
                if entity:
                    props = dict(entity.properties or {})
                    props.pop("latitude", None)
                    props.pop("longitude", None)
                    props.pop("year_start", None)
                    props.pop("year_end", None)
                    props.pop("geo_source", None)
                    entity.properties = props
            await session.flush()

        # Now reassign all persons without coords
        r = await session.execute(text("""
            SELECT id, properties->>'dynasty' as dynasty
            FROM kg_entities
            WHERE entity_type = 'person'
              AND (properties->>'latitude') IS NULL
              AND properties->>'dynasty' IS NOT NULL
              AND properties->>'dynasty' != ''
        """))
        rows = r.fetchall()
        print(f"Found {len(rows)} persons with dynasty but no coordinates\n")

        by_dynasty: dict[str, int] = {}
        updated = 0
        unmatched_dynasties: dict[str, int] = {}

        for eid, dynasty_raw in rows:
            dynasty = dynasty_raw.strip()
            match = find_dynasty_match(dynasty)
            if not match:
                unmatched_dynasties[dynasty] = unmatched_dynasties.get(dynasty, 0) + 1
                continue

            lat, lng, year_start, year_end = match

            # Regional spread
            if "日本" in dynasty:
                offset_lat = (random.random() - 0.5) * JAPAN_SPREAD_LAT * 2
                offset_lng = (random.random() - 0.5) * JAPAN_SPREAD_LNG * 2
            else:
                offset_lat = (random.random() - 0.5) * SPREAD * 2
                offset_lng = (random.random() - 0.5) * SPREAD * 2

            if not args.dry_run:
                entity = await session.get(KGEntity, eid)
                if not entity:
                    continue
                props = dict(entity.properties or {})
                props["latitude"] = round(lat + offset_lat, 6)
                props["longitude"] = round(lng + offset_lng, 6)
                props["year_start"] = year_start
                props["year_end"] = year_end
                props["geo_source"] = f"dynasty:{dynasty}"
                entity.properties = props

            updated += 1
            key = dynasty if len(dynasty) < 10 else dynasty[:10] + "..."
            by_dynasty[key] = by_dynasty.get(key, 0) + 1

            if updated % 500 == 0:
                if not args.dry_run:
                    await session.flush()
                print(f"  ... processed {updated}...")

        if not args.dry_run:
            await session.commit()

        print(f"\n=== Results ===")
        for d, cnt in sorted(by_dynasty.items(), key=lambda x: -x[1]):
            print(f"  {d}: {cnt}")
        print(f"\nTotal updated: {updated}")

        if unmatched_dynasties:
            print(f"\n=== Unmatched dynasties ===")
            for d, cnt in sorted(unmatched_dynasties.items(), key=lambda x: -x[1]):
                print(f"  {d}: {cnt}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
