"""Backfill source_code field for existing text_contents ES documents.

For each document in the text_contents index, looks up the corresponding
buddhist_texts record to find the source's code, then updates the ES document.

Usage:
    cd backend
    python scripts/backfill_content_source_code.py [--dry-run]
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_scan
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.elasticsearch import CONTENT_INDEX_NAME


async def main(dry_run: bool = False):
    es = AsyncElasticsearch(settings.es_host)
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Build text_id -> source_code mapping from DB
    print("Loading text_id -> source_code mapping from DB...")
    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT bt.id, COALESCE(ds.code, 'cbeta') AS source_code
                FROM buddhist_texts bt
                LEFT JOIN data_sources ds ON bt.source_id = ds.id
            """)
        )
        text_source_map = {row[0]: row[1] for row in result.fetchall()}

    print(f"Loaded {len(text_source_map)} text -> source mappings")

    # Scan all documents in text_contents index
    updated = 0
    skipped = 0
    missing = 0
    bulk_actions = []

    async for doc in async_scan(es, index=CONTENT_INDEX_NAME, query={"query": {"match_all": {}}}):
        src = doc["_source"]
        existing_code = src.get("source_code")
        text_id = src.get("text_id")

        if existing_code:
            skipped += 1
            continue

        source_code = text_source_map.get(text_id)
        if not source_code:
            missing += 1
            continue

        if dry_run:
            updated += 1
            continue

        bulk_actions.append({
            "update": {
                "_index": CONTENT_INDEX_NAME,
                "_id": doc["_id"],
            }
        })
        bulk_actions.append({
            "doc": {"source_code": source_code}
        })

        # Flush every 500 updates
        if len(bulk_actions) >= 1000:
            await es.bulk(body=bulk_actions, refresh=False)
            updated += len(bulk_actions) // 2
            bulk_actions = []

    # Flush remaining
    if bulk_actions:
        await es.bulk(body=bulk_actions, refresh=False)
        updated += len(bulk_actions) // 2

    if not dry_run and updated > 0:
        await es.indices.refresh(index=CONTENT_INDEX_NAME)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Done: {updated} updated, {skipped} already had source_code, {missing} text_id not found in DB")

    await es.close()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill source_code in text_contents ES index")
    parser.add_argument("--dry-run", action="store_true", help="Count without writing")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
