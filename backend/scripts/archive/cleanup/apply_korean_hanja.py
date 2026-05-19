"""Apply Korean→Hanja mapping, with validation to filter bad extractions."""
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

INPUT = "data/korean_hanja_map.json"

# Valid temple suffixes in Hanja
VALID_SUFFIXES = ["寺", "庵", "院", "宮", "堂", "閣", "樓", "塔"]
# Non-temple suffixes (exclude these)
INVALID_SUFFIXES = ["址", "山", "州", "市", "郡", "村", "峰", "鄕校"]


def clean_hanja(hanja: str) -> str | None:
    """Normalize Hanja: strip province suffixes, ruins markers, extract core name."""
    if not hanja or len(hanja) < 2 or len(hanja) > 15:
        return None
    # Strip trailing 址 (ruins marker)
    hanja = hanja.rstrip("址").strip()
    # Strip province/location in parens: e.g., "月精寺 (黃海南道)" → "月精寺"
    hanja = re.sub(r"\s*[\(（][^)）]+[\)）]\s*$", "", hanja).strip()
    # Strip leading mountain names: find the 寺/庵/院/堂/舍 and take from last such word
    m = re.search(r"[一-龥]+?(寺|庵|院|堂|舍|宮)$", hanja)
    if m:
        # Take the shorter form if the whole string looks like "山 + 寺"
        result = m.group(0)
        if len(result) >= 2 and len(result) <= 8:
            return result
    return hanja if 2 <= len(hanja) <= 10 else None


def is_valid_hanja(hanja: str, korean_name: str) -> bool:
    if not hanja or len(hanja) < 2 or len(hanja) > 10:
        return False
    # Must end with valid temple suffix
    if not any(hanja.endswith(s) for s in ["寺", "庵", "院", "堂", "舍", "宮"]):
        return False
    # Korean suffix consistency check
    if korean_name.endswith("사") and not any(hanja.endswith(s) for s in ["寺", "院", "庵", "堂", "舍"]):
        return False
    if korean_name.endswith("암") and not hanja.endswith("庵"):
        return False
    if korean_name.endswith("원") and not hanja.endswith("院"):
        return False
    return True


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(INPUT, encoding="utf-8") as f:
        hanja_map = json.load(f)

    # Filter valid mappings
    valid_mappings: dict[str, str] = {}
    rejected = 0
    for ko, entry in hanja_map.items():
        raw = entry.get("hanja")
        if not raw:
            continue
        cleaned = clean_hanja(raw)
        if cleaned and is_valid_hanja(cleaned, ko):
            valid_mappings[ko] = cleaned
        else:
            rejected += 1

    print(f"\nValid mappings: {len(valid_mappings)}")
    print(f"Rejected: {rejected}")

    if args.dry_run:
        print("\nSample mappings:")
        for ko, hanja in list(valid_mappings.items())[:20]:
            print(f"  {ko} → {hanja}")
        return

    # Apply to DB
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        updated = 0
        for ko_name, hanja in valid_mappings.items():
            r = await session.execute(text("""
                UPDATE kg_entities SET name_zh = :hanja
                WHERE name_zh = :ko AND (properties->>'latitude') IS NOT NULL
                RETURNING id
            """), {"hanja": hanja, "ko": ko_name})
            count = len(r.fetchall())
            if count > 0:
                updated += count
        await session.commit()
        print(f"\nUpdated {updated} entities with Hanja names")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
