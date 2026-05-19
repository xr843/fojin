"""
Import DILA (Dharma Drum Institute of Liberal Arts) authority database.

DILA Authority DB provides standardized data for Buddhist persons,
places, and time periods. This script enhances existing KGEntity records
by querying the DILA getAuthorityData.php endpoint per entity name.

The DILA API is a per-ID/name lookup (JSONP), not a paginated list.
Strategy: iterate existing KG entities → query DILA by name → enhance.

Usage:
    python scripts/import_dila_authority.py
    python scripts/import_dila_authority.py --type person
    python scripts/import_dila_authority.py --limit 10
"""

import argparse
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from scripts.base_importer import BaseImporter
from sqlalchemy import select

from app.models.knowledge_graph import KGEntity

DILA_BASE = "https://authority.dila.edu.tw"
DILA_WIDGET_API = f"{DILA_BASE}/webwidget/getAuthorityData.php"


def parse_jsonp(text: str) -> dict:
    """Parse JSONP response like 'cb({...})' into a Python dict."""
    # Strip the callback wrapper: cb({...})
    m = re.match(r"[^(]*\((.+)\)\s*$", text, re.DOTALL)
    if not m:
        return {}
    json_str = m.group(1)
    try:
        result = json.loads(json_str)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError:
        # DILA sometimes has trailing garbage; try to extract the outermost {}
        depth = 0
        start = json_str.find("{")
        if start < 0:
            return {}
        end = -1
        for i in range(start, len(json_str)):
            ch = json_str[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > start:
            try:
                result = json.loads(json_str[start: end + 1])
                return result if isinstance(result, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def extract_dila_entries(data: dict) -> list[dict]:
    """Extract all data entries (data1, data2, ...) from DILA response."""
    entries = []
    for key in sorted(data.keys()):
        if key.startswith("data") and isinstance(data[key], dict):
            entries.append(data[key])
    return entries


class DILAAuthorityImporter(BaseImporter):
    SOURCE_CODE = "dila"
    SOURCE_NAME_ZH = "DILA 权威数据库"
    SOURCE_NAME_EN = "Dharma Drum Institute of Liberal Arts Authority Database"
    SOURCE_BASE_URL = DILA_BASE
    SOURCE_API_URL = DILA_WIDGET_API
    SOURCE_DESCRIPTION = "法鼓文理学院佛学权威数据库，提供人名、地名、时代等规范数据"
    RATE_LIMIT_DELAY = 1.0

    def __init__(self, limit: int = 0, entity_type: str | None = None):
        super().__init__()
        self.limit = limit
        self.entity_type = entity_type

    async def query_dila(self, auth_type: str, query: str) -> list[dict]:
        """Query DILA authority by type and name/ID. Returns list of entries."""
        try:
            resp = await self.rate_limited_get(
                DILA_WIDGET_API,
                params={"type": auth_type, "id": query, "jsoncallback": "cb"},
            )
            data = parse_jsonp(resp.text)
            return extract_dila_entries(data)
        except httpx.HTTPStatusError:
            # 404/500 etc — DILA has no data for this query
            return []
        except Exception as e:
            self.stats.errors += 1
            print(f"    API error for {auth_type}/{query}: {e}")
            return []

    def _best_person_match(self, entries: list[dict], name_zh: str) -> dict | None:
        """Pick the best matching person entry from DILA results.

        Prefers exact name match; among exact matches, prefers the one
        with the most biographical data (dates, description).
        """
        exact = [e for e in entries if e.get("name") == name_zh]
        candidates = exact if exact else entries

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Score by data richness
        def score(e: dict) -> int:
            s = 0
            if e.get("bornDateBegin"):
                s += 1
            if e.get("diedDateBegin"):
                s += 1
            if e.get("note"):
                s += len(e["note"][:200])
            if e.get("names"):
                s += 1
            return s

        return max(candidates, key=score)

    async def import_persons(self, session):
        """Enhance existing person entities from DILA (idempotent).

        For each person entity without a DILA ID, query DILA by name_zh,
        then enhance with authority ID, dates, and description.
        """
        print("\n  Importing DILA person authority data...")

        result = await session.execute(
            select(KGEntity)
            .where(KGEntity.entity_type == "person")
            .order_by(KGEntity.id)
        )
        existing = list(result.scalars().all())
        print(f"  Found {len(existing)} existing person entities to enhance.")

        enhanced = 0
        skipped = 0
        errors = 0

        for entity in existing:
            if self.limit and enhanced >= self.limit:
                break

            # Skip if already has DILA data
            if entity.external_ids and entity.external_ids.get("dila"):
                skipped += 1
                continue

            if not entity.name_zh:
                continue

            entries = await self.query_dila("person", entity.name_zh)
            if not entries:
                continue

            match = self._best_person_match(entries, entity.name_zh)
            if not match:
                continue

            dila_id = match.get("authorityID", "")
            name = match.get("name", "")
            note = match.get("note", "")
            born = match.get("bornDateBegin", "")
            died = match.get("diedDateBegin", "")
            dynasty = match.get("dynasty", "")
            names_str = match.get("names", "")

            # Verify name match (DILA search can return partial matches)
            if (
                name and name != entity.name_zh
                and entity.name_zh not in (names_str or "")
                and entity.name_zh not in (name or "")
            ):
                continue

            changed = False

            # Merge DILA authority ID
            if dila_id:
                ext_ids = dict(entity.external_ids or {})
                if ext_ids.get("dila") != dila_id:
                    ext_ids["dila"] = dila_id
                    entity.external_ids = ext_ids
                    changed = True

            # Enhance description
            if note and not entity.description:
                # Truncate overly long notes
                entity.description = note[:500] if len(note) > 500 else note
                changed = True

            # Enhance properties with dates and dynasty
            props = dict(entity.properties or {})
            if born and not props.get("birth_date"):
                props["birth_date"] = born
                changed = True
            if died and not props.get("death_date"):
                props["death_date"] = died
                changed = True
            if dynasty and not props.get("dynasty"):
                props["dynasty"] = dynasty
                changed = True
            if changed and props:
                entity.properties = props

            if changed:
                enhanced += 1
                if enhanced % 20 == 0:
                    await session.flush()
                    print(f"    Enhanced {enhanced} persons so far...")

        await session.flush()
        self.stats.texts_updated += enhanced
        print(f"  Person import done: {enhanced} enhanced, {skipped} already had DILA data, {errors} errors.")

    async def import_places(self, session):
        """Enhance existing place entities from DILA (idempotent)."""
        print("\n  Importing DILA place authority data...")

        result = await session.execute(
            select(KGEntity)
            .where(KGEntity.entity_type == "place")
            .order_by(KGEntity.id)
        )
        existing = list(result.scalars().all())
        print(f"  Found {len(existing)} existing place entities.")

        enhanced = 0
        skipped = 0

        for entity in existing:
            if self.limit and enhanced >= self.limit:
                break

            if entity.external_ids and entity.external_ids.get("dila"):
                skipped += 1
                continue

            if not entity.name_zh:
                continue

            entries = await self.query_dila("place", entity.name_zh)
            if not entries:
                continue

            # Pick best match: prefer exact name match
            match = None
            for e in entries:
                if e.get("name") == entity.name_zh:
                    match = e
                    break
            if not match and entries:
                match = entries[0]
            if not match:
                continue

            dila_id = match.get("authorityID", "")
            note = match.get("note", "")
            lat = match.get("lat", "")
            lng = match.get("long", "")
            district = match.get("districtModern", "")

            # Verify name match
            if (
                match.get("name") and match["name"] != entity.name_zh
                and entity.name_zh not in (match.get("names", "") or "")
            ):
                continue

            changed = False

            if dila_id:
                ext_ids = dict(entity.external_ids or {})
                if ext_ids.get("dila") != dila_id:
                    ext_ids["dila"] = dila_id
                    entity.external_ids = ext_ids
                    changed = True

            if note and not entity.description:
                entity.description = note[:500] if len(note) > 500 else note
                changed = True

            props = dict(entity.properties or {})
            if lat and lng and not props.get("latitude"):
                props["latitude"] = float(lat) if lat else None
                props["longitude"] = float(lng) if lng else None
                changed = True
            if district and not props.get("district_modern"):
                props["district_modern"] = district
                changed = True
            if changed and props:
                entity.properties = props

            if changed:
                enhanced += 1
                if enhanced % 20 == 0:
                    await session.flush()
                    print(f"    Enhanced {enhanced} places so far...")

        await session.flush()
        self.stats.texts_updated += enhanced
        print(f"  Place import done: {enhanced} enhanced, {skipped} already had DILA data.")

    async def run_import(self):
        async with self.session_factory() as session:
            await self.ensure_source(session)

            if self.entity_type in (None, "person"):
                await self.import_persons(session)

            if self.entity_type in (None, "place"):
                await self.import_places(session)

            await session.commit()


async def main():
    parser = argparse.ArgumentParser(description="Import DILA authority data")
    parser.add_argument("--limit", type=int, default=0, help="Limit per entity type")
    parser.add_argument("--type", dest="entity_type", choices=["person", "place"],
                        help="Import only specific entity type")
    args = parser.parse_args()

    importer = DILAAuthorityImporter(limit=args.limit, entity_type=args.entity_type)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
