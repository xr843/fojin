"""
Incremental sync of DILA person authority database.

Fetches new person records from DILA API starting from the max DILA ID
already in our database. Stops after 100 consecutive empty IDs.

Supports --full mode to check all existing records for updates.

Usage:
    python scripts/sync_dila_incremental.py           # incremental
    python scripts/sync_dila_incremental.py --full     # full check
    python scripts/sync_dila_incremental.py --dry-run  # preview only
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

DILA_WIDGET_API = "https://authority.dila.edu.tw/webwidget/getAuthorityData.php"
MAX_CONSECUTIVE_EMPTY = 100
REQUEST_DELAY = 0.5  # seconds between API calls


def parse_jsonp(text_: str) -> dict | None:
    """Parse JSONP response like 'cb({...})' into a Python dict."""
    m = re.match(r"[^(]*\((.+)\)\s*$", text_, re.DOTALL)
    if not m:
        return None
    json_str = m.group(1)
    if json_str.strip() == "null":
        return None
    try:
        result = json.loads(json_str)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def extract_person_data(data: dict) -> dict | None:
    """Extract person info from DILA API response."""
    # Find first data entry
    for key in sorted(data.keys()):
        if key.startswith("data") and isinstance(data[key], dict):
            entry = data[key]
            return {
                "dila_id": entry.get("authorityID", ""),
                "name_zh": entry.get("name", ""),
                "gender": entry.get("gender", ""),
                "is_monk": entry.get("monk", "") == "y",
                "born": entry.get("bornDateBegin", ""),
                "died": entry.get("diedDateBegin", ""),
                "dynasty": entry.get("dynasty", ""),
                "note": entry.get("note", ""),
                "names": entry.get("names", ""),
                "pinyin": entry.get("pinyin", {}),
            }
    return None


async def fetch_person(client: httpx.AsyncClient, dila_id: str) -> dict | None:
    """Fetch a single person from DILA API."""
    try:
        resp = await client.get(
            DILA_WIDGET_API,
            params={"type": "person", "id": dila_id, "jsoncallback": "cb"},
            timeout=15,
        )
        data = parse_jsonp(resp.text)
        if not data:
            return None
        return extract_person_data(data)
    except Exception as e:
        print(f"  ERR fetching {dila_id}: {e}")
        return None


def clean_html(text_: str) -> str:
    """Remove HTML tags from note text."""
    return re.sub(r"<[^>]+>", "", text_) if text_ else ""


async def get_max_dila_id(session: AsyncSession) -> int:
    """Get the max numeric part of DILA person IDs in our DB."""
    result = await session.execute(text(
        "SELECT max(external_ids->>'dila') FROM kg_entities "
        "WHERE external_ids->>'dila' LIKE 'A%'"
    ))
    max_id = result.scalar()
    if max_id:
        return int(max_id[1:])  # strip 'A' prefix
    return 0


async def sync_incremental(session: AsyncSession, dry_run: bool = False):
    """Fetch new DILA persons starting from max ID + 1."""
    max_num = await get_max_dila_id(session)
    print(f"Current max DILA person ID: A{max_num:06d}")

    current = max_num + 1
    consecutive_empty = 0
    new_count = 0
    errors = 0

    async with httpx.AsyncClient() as client:
        while consecutive_empty < MAX_CONSECUTIVE_EMPTY:
            dila_id = f"A{current:06d}"
            person = await fetch_person(client, dila_id)
            await asyncio.sleep(REQUEST_DELAY)

            if not person or not person["name_zh"]:
                consecutive_empty += 1
                current += 1
                continue

            consecutive_empty = 0
            name = person["name_zh"]
            note = clean_html(person.get("note", ""))

            # Check if already exists by dila_id
            existing = await session.execute(text(
                "SELECT id FROM kg_entities WHERE external_ids->>'dila' = :dila_id"
            ), {"dila_id": dila_id})
            if existing.scalar():
                print(f"  SKIP {dila_id} {name} (already exists)")
                current += 1
                continue

            # Build properties
            props = {}
            if person["born"] and person["born"] != "unknown":
                props["birth_date"] = person["born"]
            if person["died"] and person["died"] != "unknown":
                props["death_date"] = person["died"]
            if person["dynasty"] and person["dynasty"] != "沒有給定朝代":
                props["dynasty"] = person["dynasty"]
            if person["gender"]:
                props["gender"] = "male" if person["gender"] == "1" else "female" if person["gender"] == "2" else None
            if person["is_monk"]:
                props["is_monastic"] = True
            # Pinyin
            pinyin = person.get("pinyin", {})
            if isinstance(pinyin, dict) and pinyin:
                props["pinyin"] = list(pinyin.values())[0]

            desc = note[:500] if note else None

            if dry_run:
                print(f"  NEW {dila_id} {name} - {desc[:60] if desc else '(no desc)'}")
            else:
                await session.execute(text("""
                    INSERT INTO kg_entities (entity_type, name_zh, description, properties, external_ids)
                    VALUES ('person', :name_zh, :description, cast(:properties as json), cast(:external_ids as json))
                """), {
                    "name_zh": name,
                    "description": desc,
                    "properties": json.dumps(props) if props else "{}",
                    "external_ids": json.dumps({"dila": dila_id}),
                })
                print(f"  ADD {dila_id} {name}")

            new_count += 1
            current += 1

            if new_count % 50 == 0 and not dry_run:
                await session.commit()
                print(f"  ... committed {new_count} so far")

    if not dry_run and new_count > 0:
        await session.commit()

    print(f"\nIncremental sync done: {new_count} new persons, scanned up to A{current-1:06d}")
    return new_count


async def sync_full(session: AsyncSession, dry_run: bool = False):
    """Check all existing DILA persons for updates (description/dates)."""
    result = await session.execute(text(
        "SELECT id, external_ids->>'dila' AS dila_id, name_zh, description, properties "
        "FROM kg_entities WHERE external_ids->>'dila' LIKE 'A%' ORDER BY external_ids->>'dila'"
    ))
    rows = result.fetchall()
    print(f"Full check: {len(rows)} existing DILA persons")

    updated = 0
    async with httpx.AsyncClient() as client:
        for i, (eid, dila_id, name_zh, desc, props) in enumerate(rows):
            person = await fetch_person(client, dila_id)
            await asyncio.sleep(REQUEST_DELAY)

            if not person:
                continue

            props = dict(props or {})
            changes = []
            note = clean_html(person.get("note", ""))

            # Update description if we have none but DILA has one
            new_desc = desc
            if note and not desc:
                new_desc = note[:500]
                changes.append("desc")

            # Update dates
            if person["born"] and person["born"] != "unknown" and not props.get("birth_date"):
                props["birth_date"] = person["born"]
                changes.append("birth")
            if person["died"] and person["died"] != "unknown" and not props.get("death_date"):
                props["death_date"] = person["died"]
                changes.append("death")
            if person["dynasty"] and person["dynasty"] != "沒有給定朝代" and not props.get("dynasty"):
                props["dynasty"] = person["dynasty"]
                changes.append("dynasty")

            if changes:
                if dry_run:
                    print(f"  UPD {dila_id} {name_zh}: {', '.join(changes)}")
                else:
                    await session.execute(text("""
                        UPDATE kg_entities
                        SET description = :desc,
                            properties = cast(:props as json)
                        WHERE id = :id
                    """), {
                        "id": eid,
                        "desc": new_desc,
                        "props": json.dumps(props),
                    })
                updated += 1

            if (i + 1) % 200 == 0:
                if not dry_run and updated > 0:
                    await session.commit()
                print(f"  [{i+1}/{len(rows)}] checked, {updated} updated")

    if not dry_run and updated > 0:
        await session.commit()

    print(f"\nFull sync done: {updated} updated out of {len(rows)} checked")
    return updated


async def main():
    parser = argparse.ArgumentParser(description="Incremental DILA person sync")
    parser.add_argument("--full", action="store_true", help="Full check for updates")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    print("=" * 60)
    print(f"DILA Incremental Sync — {datetime.now().isoformat()}")
    print(f"Mode: {'full' if args.full else 'incremental'} {'(dry-run)' if args.dry_run else ''}")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        new = await sync_incremental(session, dry_run=args.dry_run)

        if args.full:
            await sync_full(session, dry_run=args.dry_run)

    await engine.dispose()
    print(f"\n{'=' * 60}")
    print(f"Finished at {datetime.now().isoformat()}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
