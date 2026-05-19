"""
Enrich KG entities with geographic coordinates from Wikidata.

Strategy:
1. Query Wikidata SPARQL for Buddhist monasteries/temples/places with coordinates
2. Query Wikidata for Buddhist scholars/monks with birth/activity place coordinates
3. Match against existing FoJin KG entities by name (zh/en/sa/pi)
4. Update properties with latitude/longitude

Usage:
    cd backend
    python -m scripts.enrich_wikidata_geo [--dry-run] [--limit 5000]
"""

import argparse
import asyncio
import os
import sys
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.models.knowledge_graph import KGEntity

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist studies platform)"

# SPARQL: Buddhist monasteries, temples, stupas, caves with coordinates + Chinese/English labels
SPARQL_PLACES = """
SELECT ?item ?itemLabel ?itemLabelZh ?coord ?itemDescription WHERE {
  {
    ?item wdt:P31/wdt:P279* wd:Q160742 .  # Buddhist monastery
  } UNION {
    ?item wdt:P31/wdt:P279* wd:Q5393308 .  # Buddhist temple
  } UNION {
    ?item wdt:P31/wdt:P279* wd:Q178561 .   # Stupa
  } UNION {
    ?item wdt:P31/wdt:P279* wd:Q1030034 .  # Cave temple
  } UNION {
    ?item wdt:P31/wdt:P279* wd:Q839954 .   # Archaeological site
    ?item wdt:P361*/wdt:P31/wdt:P279* wd:Q748 .  # related to Buddhism
  }
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }
  OPTIONAL { ?item schema:description ?itemDescription FILTER(LANG(?itemDescription) = "zh") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
"""

# SPARQL: Buddhist scholars, monks with birth/death place coordinates
SPARQL_PERSONS = """
SELECT ?item ?itemLabel ?itemLabelZh ?coord ?placeLabel WHERE {
  {
    ?item wdt:P106/wdt:P279* wd:Q4263842 .  # Buddhist monk
  } UNION {
    ?item wdt:P106/wdt:P279* wd:Q1662844 .  # Buddhist priest
  } UNION {
    ?item wdt:P140 wd:Q748 .                 # religion: Buddhism
    ?item wdt:P106/wdt:P279* wd:Q1234713 .  # theologian
  }
  {
    ?item wdt:P19 ?place .  # birth place
  } UNION {
    ?item wdt:P20 ?place .  # death place
  }
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
"""

# SPARQL: Important Buddhist sites (Eight Great Places, etc.)
SPARQL_HOLY_SITES = """
SELECT ?item ?itemLabel ?itemLabelZh ?coord ?itemDescription WHERE {
  ?item wdt:P31/wdt:P279* wd:Q1068507 .  # Sacred place
  ?item wdt:P625 ?coord .
  {
    ?item wdt:P361*/wdt:P31/wdt:P279* wd:Q748 .  # related to Buddhism
  } UNION {
    ?item rdfs:label ?lbl FILTER(LANG(?lbl) = "en")
    FILTER(CONTAINS(LCASE(?lbl), "buddha") || CONTAINS(LCASE(?lbl), "bodhi"))
  }
  OPTIONAL { ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }
  OPTIONAL { ?item schema:description ?itemDescription FILTER(LANG(?itemDescription) = "zh") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
"""


def parse_point(coord_str: str) -> tuple[float, float] | None:
    """Parse 'Point(lng lat)' WKT literal from Wikidata."""
    if not coord_str or not coord_str.startswith("Point("):
        return None
    inner = coord_str.removeprefix("Point(").removesuffix(")")
    parts = inner.split()
    if len(parts) != 2:
        return None
    try:
        lng, lat = float(parts[0]), float(parts[1])
        if -180 <= lng <= 180 and -90 <= lat <= 90:
            return lat, lng
    except ValueError:
        pass
    return None


async def query_wikidata(http: httpx.AsyncClient, sparql: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata and return parsed results."""
    for attempt in range(3):
        try:
            resp = await http.get(
                WIKIDATA_SPARQL_URL,
                params={"query": sparql, "format": "json"},
                headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
                timeout=120.0,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                print(f"  Rate limited by Wikidata. Waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", {}).get("bindings", [])
        except Exception as e:
            if attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"  SPARQL error: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                print(f"  SPARQL failed after 3 attempts: {e}")
                return []
    return []


def extract_place_records(bindings: list[dict]) -> list[dict]:
    """Extract place records from SPARQL results."""
    records = []
    seen = set()
    for b in bindings:
        wikidata_id = b.get("item", {}).get("value", "").split("/")[-1]
        if not wikidata_id or wikidata_id in seen:
            continue
        seen.add(wikidata_id)

        coord_val = b.get("coord", {}).get("value", "")
        parsed = parse_point(coord_val)
        if not parsed:
            continue
        lat, lng = parsed

        name_en = b.get("itemLabel", {}).get("value", "")
        name_zh = b.get("itemLabelZh", {}).get("value", "")
        desc = b.get("itemDescription", {}).get("value", "")

        # Skip if name_en is just the Q-id (no label)
        if name_en.startswith("Q") and name_en[1:].isdigit():
            name_en = ""

        if not name_zh and not name_en:
            continue

        records.append({
            "wikidata_id": wikidata_id,
            "name_zh": name_zh,
            "name_en": name_en,
            "description": desc,
            "latitude": lat,
            "longitude": lng,
        })
    return records


def extract_person_records(bindings: list[dict]) -> list[dict]:
    """Extract person records from SPARQL results (with place coordinates)."""
    records = []
    seen = set()
    for b in bindings:
        wikidata_id = b.get("item", {}).get("value", "").split("/")[-1]
        if not wikidata_id or wikidata_id in seen:
            continue
        seen.add(wikidata_id)

        coord_val = b.get("coord", {}).get("value", "")
        parsed = parse_point(coord_val)
        if not parsed:
            continue
        lat, lng = parsed

        name_en = b.get("itemLabel", {}).get("value", "")
        name_zh = b.get("itemLabelZh", {}).get("value", "")
        place_name = b.get("placeLabel", {}).get("value", "")

        if name_en.startswith("Q") and name_en[1:].isdigit():
            name_en = ""

        if not name_zh and not name_en:
            continue

        records.append({
            "wikidata_id": wikidata_id,
            "name_zh": name_zh,
            "name_en": name_en,
            "place_name": place_name,
            "latitude": lat,
            "longitude": lng,
        })
    return records


def normalize_zh(s: str) -> str:
    """Normalize Chinese name for matching: strip whitespace and common suffixes."""
    return s.strip().replace(" ", "")


async def match_and_update(
    session: AsyncSession,
    records: list[dict],
    entity_types: list[str],
    dry_run: bool,
) -> tuple[int, int]:
    """Match Wikidata records to existing KG entities and update coordinates.

    Returns (matched_count, updated_count).
    """
    # Load all entities of the given types that lack coordinates
    result = await session.execute(
        select(KGEntity).where(
            KGEntity.entity_type.in_(entity_types),
        )
    )
    entities = list(result.scalars().all())

    # Build lookup indexes by name
    by_zh: dict[str, list[KGEntity]] = {}
    by_en: dict[str, list[KGEntity]] = {}
    by_sa: dict[str, list[KGEntity]] = {}

    for e in entities:
        if e.name_zh:
            key = normalize_zh(e.name_zh)
            by_zh.setdefault(key, []).append(e)
        if e.name_en:
            by_en.setdefault(e.name_en.lower().strip(), []).append(e)
        if e.name_sa:
            by_sa.setdefault(e.name_sa.lower().strip(), []).append(e)

    matched = 0
    updated = 0

    for rec in records:
        # Try to match by Chinese name first, then English
        candidates = []
        if rec["name_zh"]:
            key = normalize_zh(rec["name_zh"])
            candidates = by_zh.get(key, [])
        if not candidates and rec["name_en"]:
            candidates = by_en.get(rec["name_en"].lower().strip(), [])

        if not candidates:
            continue

        matched += 1
        for entity in candidates:
            props = dict(entity.properties or {})
            if props.get("latitude") and props.get("longitude"):
                continue  # Already has coordinates

            props["latitude"] = rec["latitude"]
            props["longitude"] = rec["longitude"]

            # Store Wikidata ID for provenance
            ext_ids = dict(entity.external_ids or {})
            if not ext_ids.get("wikidata"):
                ext_ids["wikidata"] = rec["wikidata_id"]
                entity.external_ids = ext_ids

            if not dry_run:
                entity.properties = props

            updated += 1
            print(f"  + {entity.name_zh} ({entity.entity_type}) "
                  f"← ({rec['latitude']:.4f}, {rec['longitude']:.4f}) "
                  f"[{rec['wikidata_id']}]")

    return matched, updated


async def propagate_active_in_coords(session: AsyncSession, dry_run: bool) -> int:
    """For person entities without coordinates, inherit from their active_in place."""
    # Find persons without coords that have active_in relations to places with coords
    sql = """
        SELECT DISTINCT ON (p.id)
            p.id AS person_id,
            pl.name_zh AS place_name,
            (pl.properties->>'latitude')::float AS lat,
            (pl.properties->>'longitude')::float AS lng
        FROM kg_entities p
        JOIN kg_relations r ON r.subject_id = p.id AND r.predicate = 'active_in'
        JOIN kg_entities pl ON pl.id = r.object_id
        WHERE p.entity_type = 'person'
          AND (p.properties->>'latitude') IS NULL
          AND (pl.properties->>'latitude') IS NOT NULL
        ORDER BY p.id, r.confidence DESC
    """
    from sqlalchemy import text
    result = await session.execute(text(sql))
    rows = result.fetchall()

    count = 0
    for row in rows:
        person_id, place_name, lat, lng = row
        entity = await session.get(KGEntity, person_id)
        if not entity:
            continue

        props = dict(entity.properties or {})
        if props.get("latitude"):
            continue

        props["latitude"] = lat
        props["longitude"] = lng
        props["geo_source"] = f"active_in:{place_name}"

        if not dry_run:
            entity.properties = props

        count += 1
        if count <= 20:
            print(f"  + {entity.name_zh} ← {place_name} ({lat:.4f}, {lng:.4f})")

    if count > 20:
        print(f"  ... and {count - 20} more")

    return count


async def main():
    parser = argparse.ArgumentParser(description="Enrich KG entities with Wikidata coordinates")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--limit", type=int, default=10000, help="Max records per query")
    args = parser.parse_args()

    print("=" * 60)
    print("佛津 (FoJin) — Wikidata Geographic Enrichment")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN — no changes will be written\n")

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with httpx.AsyncClient() as http:
        # Phase 1: Buddhist places (monasteries, temples, stupas, caves)
        print("\n[Phase 1] Querying Wikidata for Buddhist places...")
        t0 = time.time()
        place_bindings = await query_wikidata(http, SPARQL_PLACES)
        print(f"  Received {len(place_bindings)} results ({time.time() - t0:.1f}s)")
        place_records = extract_place_records(place_bindings)
        print(f"  Extracted {len(place_records)} unique places with coordinates")

        # Phase 2: Holy sites
        print("\n[Phase 2] Querying Wikidata for Buddhist holy sites...")
        await asyncio.sleep(2)  # Be polite to Wikidata
        t0 = time.time()
        holy_bindings = await query_wikidata(http, SPARQL_HOLY_SITES)
        print(f"  Received {len(holy_bindings)} results ({time.time() - t0:.1f}s)")
        holy_records = extract_place_records(holy_bindings)
        print(f"  Extracted {len(holy_records)} unique holy sites")

        # Merge place records (deduplicate by wikidata_id)
        seen_ids = {r["wikidata_id"] for r in place_records}
        for r in holy_records:
            if r["wikidata_id"] not in seen_ids:
                place_records.append(r)
                seen_ids.add(r["wikidata_id"])
        print(f"\n  Total unique place records: {len(place_records)}")

        # Phase 3: Buddhist persons
        print("\n[Phase 3] Querying Wikidata for Buddhist persons with place coordinates...")
        await asyncio.sleep(2)
        t0 = time.time()
        person_bindings = await query_wikidata(http, SPARQL_PERSONS)
        print(f"  Received {len(person_bindings)} results ({time.time() - t0:.1f}s)")
        person_records = extract_person_records(person_bindings)
        print(f"  Extracted {len(person_records)} unique persons with coordinates")

    # Phase 4: Match and update database
    async with session_factory() as session:
        print("\n[Phase 4] Matching places to KG entities...")
        p_matched, p_updated = await match_and_update(
            session, place_records, ["place", "monastery"], args.dry_run,
        )
        print(f"  Places: {p_matched} matched, {p_updated} updated")

        print("\n[Phase 5] Matching persons to KG entities...")
        per_matched, per_updated = await match_and_update(
            session, person_records, ["person"], args.dry_run,
        )
        print(f"  Persons: {per_matched} matched, {per_updated} updated")

        print("\n[Phase 6] Propagating coordinates via active_in relations...")
        propagated = await propagate_active_in_coords(session, args.dry_run)
        print(f"  Propagated: {propagated} persons got coordinates from their places")

        if not args.dry_run:
            await session.commit()
            print("\nCommitted to database.")
        else:
            print("\nDry run complete — no changes written.")

    await engine.dispose()

    total_updated = p_updated + per_updated + propagated
    print(f"\n{'=' * 60}")
    print(f"Summary: {total_updated} entities enriched with coordinates")
    print(f"  Places: {p_updated}, Persons (Wikidata): {per_updated}, Persons (active_in): {propagated}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
