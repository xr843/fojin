"""Initialize Elasticsearch indices for Buddhist texts and content.

Supports both full recreation (--recreate) and incremental mapping updates (default).
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from app.config import settings
from app.core.elasticsearch import (
    INDEX_NAME, INDEX_SETTINGS,
    CONTENT_INDEX_NAME, CONTENT_INDEX_SETTINGS,
)


async def create_index(es: AsyncElasticsearch, name: str, settings_body: dict):
    """Create or recreate an ES index."""
    if await es.indices.exists(index=name):
        print(f"Index '{name}' already exists. Deleting...")
        await es.indices.delete(index=name)

    await es.indices.create(index=name, body=settings_body)
    print(f"Index '{name}' created successfully.")


async def update_mapping(es: AsyncElasticsearch, name: str, settings_body: dict):
    """Update mapping for an existing index (incremental, non-destructive)."""
    if not await es.indices.exists(index=name):
        print(f"Index '{name}' does not exist. Creating...")
        await es.indices.create(index=name, body=settings_body)
        print(f"Index '{name}' created successfully.")
        return

    # Close index to update settings (analyzers)
    index_settings = settings_body.get("settings", {})
    if index_settings:
        try:
            await es.indices.close(index=name)
            # Only update analysis settings
            analysis = index_settings.get("analysis")
            if analysis:
                await es.indices.put_settings(
                    index=name, body={"analysis": analysis}
                )
                print(f"Index '{name}' analysis settings updated.")
            await es.indices.open(index=name)
        except Exception as e:
            # Re-open index even on failure
            try:
                await es.indices.open(index=name)
            except Exception:
                pass
            print(f"Warning: could not update settings for '{name}': {e}")

    # Update mappings (additive — new fields only)
    mappings = settings_body.get("mappings", {})
    if mappings:
        try:
            await es.indices.put_mapping(index=name, body=mappings)
            print(f"Index '{name}' mappings updated.")
        except Exception as e:
            if "Cannot update parameter [analyzer]" in str(e):
                print(f"Warning: '{name}' has analyzer conflicts on existing fields.")
                print(f"  Use --recreate to rebuild the index with new analyzers.")
            else:
                raise


async def main():
    parser = argparse.ArgumentParser(description="Initialize or update ES indices")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate indices (WARNING: destroys existing data)",
    )
    args = parser.parse_args()

    es = AsyncElasticsearch(settings.es_host)
    try:
        if args.recreate:
            print("Mode: RECREATE (destructive)")
            await create_index(es, INDEX_NAME, INDEX_SETTINGS)
            await create_index(es, CONTENT_INDEX_NAME, CONTENT_INDEX_SETTINGS)
        else:
            print("Mode: UPDATE (incremental mapping)")
            await update_mapping(es, INDEX_NAME, INDEX_SETTINGS)
            await update_mapping(es, CONTENT_INDEX_NAME, CONTENT_INDEX_SETTINGS)
        print("\nAll indices initialized.")
    finally:
        await es.close()


if __name__ == "__main__":
    asyncio.run(main())
