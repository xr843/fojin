"""
Import complete CBETA catalog from DILA-edu/cbeta-metadata.

Downloads the work-info JSON files from the DILA metadata repository
and imports all entries into PostgreSQL and Elasticsearch.
Supports ON CONFLICT DO UPDATE for idempotent re-runs.
Also auto-creates TextIdentifier for each CBETA entry.
"""

import asyncio
import json
import os
import sys

import httpx
from sqlalchemy import select, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.elasticsearch import INDEX_NAME
from app.scripts_shared import CATEGORIES, CBETA_ONLINE_BASE, parse_dynasty_translator

# DILA metadata repo URLs
DILA_BASE = "https://raw.githubusercontent.com/DILA-edu/cbeta-metadata/main"
WORK_INFO_URL = f"{DILA_BASE}/work-info/work_info.json"
ALT_WORK_INFO_URL = f"{DILA_BASE}/work-info/work-info.json"

# Fallback: cbeta-org
CBETA_ORG_URL = "https://raw.githubusercontent.com/cbeta-org/cbeta-metadata/master/catalog/catalog.json"


LOCAL_WORK_INFO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cbeta_all_works.json")


def _parse_dict_format(data: dict) -> list[dict]:
    entries = []
    for work_id, info in data.items():
        entry = {"work": work_id}
        entry["title"] = info.get("title", info.get("title_zh", ""))
        entry["byline"] = info.get("byline", "")
        entry["juan"] = info.get("juan", info.get("fascicle_count"))
        entry["category"] = info.get("category", "")
        entries.append(entry)
    return entries


async def fetch_work_info() -> list[dict]:
    """Fetch work info from local file or DILA-edu/cbeta-org metadata repos."""
    # Try local file first
    if os.path.exists(LOCAL_WORK_INFO):
        print(f"  Loading from local file: {LOCAL_WORK_INFO}")
        with open(LOCAL_WORK_INFO) as f:
            data = json.load(f)
        if isinstance(data, dict):
            entries = _parse_dict_format(data)
            print(f"  Loaded {len(entries)} entries from local file")
            return entries
        elif isinstance(data, list):
            print(f"  Loaded {len(data)} entries from local file")
            return data

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        for url in [WORK_INFO_URL, ALT_WORK_INFO_URL, CBETA_ORG_URL]:
            try:
                print(f"  Trying: {url}")
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        entries = _parse_dict_format(data)
                        print(f"  Fetched {len(entries)} entries (dict format)")
                        return entries
                    elif isinstance(data, list):
                        print(f"  Fetched {len(data)} entries (list format)")
                        return data
            except Exception as e:
                print(f"  Failed: {e}")

    print("  All remote sources failed. Using built-in sample data.")
    from import_cbeta import generate_sample_catalog
    return generate_sample_catalog()


def transform_entry(entry: dict) -> dict | None:
    """Transform a catalog entry into our database format."""
    work_id = entry.get("work", "")
    title = entry.get("title", "")

    if not work_id or not title:
        return None

    taisho_id = work_id if work_id.startswith("T") else None

    byline = entry.get("byline", "") or ""
    dynasty, translator = parse_dynasty_translator(byline)

    juan = entry.get("juan")
    if isinstance(juan, str):
        try:
            juan = int(juan)
        except ValueError:
            juan = None

    category = entry.get("category", "")
    prefix = ""
    for p in sorted(CATEGORIES.keys(), key=len, reverse=True):
        if work_id.startswith(p):
            prefix = p
            break

    collection_name = CATEGORIES.get(prefix, ("其他", "Other"))[0] if prefix else None
    cbeta_url = f"{CBETA_ONLINE_BASE}{work_id}"

    return {
        "taisho_id": taisho_id,
        "cbeta_id": work_id,
        "title_zh": title,
        "title_sa": None,
        "title_bo": None,
        "title_pi": None,
        "translator": translator,
        "dynasty": dynasty,
        "fascicle_count": juan,
        "category": category or collection_name,
        "subcategory": collection_name,
        "cbeta_url": cbeta_url,
    }


async def upsert_to_postgres(session: AsyncSession, records: list[dict]) -> dict[str, int]:
    """Upsert records to PostgreSQL with ON CONFLICT DO UPDATE."""
    id_map = {}
    for i, rec in enumerate(records):
        result = await session.execute(
            text("""
                INSERT INTO buddhist_texts
                    (taisho_id, cbeta_id, title_zh, title_sa, title_bo, title_pi,
                     translator, dynasty, fascicle_count, category, subcategory, cbeta_url)
                VALUES
                    (:taisho_id, :cbeta_id, :title_zh, :title_sa, :title_bo, :title_pi,
                     :translator, :dynasty, :fascicle_count, :category, :subcategory, :cbeta_url)
                ON CONFLICT (cbeta_id) DO UPDATE SET
                    taisho_id = EXCLUDED.taisho_id,
                    title_zh = EXCLUDED.title_zh,
                    translator = EXCLUDED.translator,
                    dynasty = EXCLUDED.dynasty,
                    fascicle_count = EXCLUDED.fascicle_count,
                    category = EXCLUDED.category,
                    subcategory = EXCLUDED.subcategory,
                    cbeta_url = EXCLUDED.cbeta_url
                RETURNING id
            """),
            rec,
        )
        row = result.fetchone()
        id_map[rec["cbeta_id"]] = row[0]

        if (i + 1) % 1000 == 0:
            print(f"  PostgreSQL: upserted {i + 1}/{len(records)} records...")
            await session.flush()

    await session.commit()
    return id_map


async def create_text_identifiers(session: AsyncSession, id_map: dict[str, int]):
    """Create TextIdentifier records for each CBETA entry."""
    # Ensure CBETA source exists
    result = await session.execute(
        text("SELECT id FROM data_sources WHERE code = 'cbeta'")
    )
    row = result.fetchone()
    if not row:
        result = await session.execute(
            text("""
                INSERT INTO data_sources (code, name_zh, name_en, base_url, description)
                VALUES ('cbeta', 'CBETA 中華電子佛典協會', 'Chinese Buddhist Electronic Text Association',
                        'https://www.cbeta.org', '中華電子佛典協會，收録漢文佛典')
                ON CONFLICT (code) DO NOTHING
                RETURNING id
            """)
        )
        row = result.fetchone()
        if not row:
            result = await session.execute(
                text("SELECT id FROM data_sources WHERE code = 'cbeta'")
            )
            row = result.fetchone()
        await session.flush()

    source_id = row[0]
    count = 0

    for cbeta_id, text_id in id_map.items():
        await session.execute(
            text("""
                INSERT INTO text_identifiers (text_id, source_id, source_uid, source_url)
                VALUES (:text_id, :source_id, :source_uid, :source_url)
                ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
            """),
            {
                "text_id": text_id,
                "source_id": source_id,
                "source_uid": cbeta_id,
                "source_url": f"https://cbetaonline.dila.edu.tw/zh/{cbeta_id}",
            },
        )
        count += 1

        if count % 1000 == 0:
            await session.flush()
            print(f"  TextIdentifiers: created {count}/{len(id_map)}...")

    await session.commit()
    print(f"  TextIdentifiers: {count} records processed.")


async def index_to_elasticsearch(es: AsyncElasticsearch, records: list[dict], id_map: dict[str, int]):
    """Index records into Elasticsearch."""

    async def gen_actions():
        for rec in records:
            db_id = id_map.get(rec["cbeta_id"])
            if db_id is None:
                continue
            doc = {k: v for k, v in rec.items() if v is not None}
            doc["lang"] = "lzh"
            doc["source_code"] = "cbeta"
            yield {
                "_index": INDEX_NAME,
                "_id": str(db_id),
                "_source": {"id": db_id, **doc},
            }

    success, errors = await async_bulk(es, gen_actions(), raise_on_error=False)
    err_count = len(errors) if isinstance(errors, list) else errors
    print(f"  Elasticsearch: indexed {success} documents, {err_count} errors")


async def main():
    print("=" * 60)
    print("佛津 (FoJin) — Complete CBETA Catalog Import")
    print("=" * 60)

    print("\n[1/4] Fetching complete CBETA catalog...")
    raw_entries = await fetch_work_info()

    print(f"\n[2/4] Transforming {len(raw_entries)} entries...")
    records = []
    seen = set()
    for entry in raw_entries:
        rec = transform_entry(entry)
        if rec and rec["cbeta_id"] not in seen:
            records.append(rec)
            seen.add(rec["cbeta_id"])
    print(f"  Transformed {len(records)} unique valid records.")

    if not records:
        print("No records to import. Exiting.")
        return

    print(f"\n[3/4] Upserting to PostgreSQL and Elasticsearch...")
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        id_map = await upsert_to_postgres(session, records)
        print(f"  PostgreSQL: {len(id_map)} records upserted.")

    es = AsyncElasticsearch(settings.es_host)
    try:
        await index_to_elasticsearch(es, records, id_map)
    finally:
        await es.close()

    print(f"\n[4/4] Creating TextIdentifiers...")
    async with session_factory() as session:
        await create_text_identifiers(session, id_map)

    await engine.dispose()

    print(f"\nImport complete! {len(records)} Buddhist texts imported.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
