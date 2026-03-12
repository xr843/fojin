"""
Sync all buddhist_texts from PostgreSQL to Elasticsearch.
Use this when ES index needs to be rebuilt from existing PG data.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.elasticsearch import INDEX_NAME


async def main():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    es = AsyncElasticsearch(settings.ELASTICSEARCH_URL)

    async with session_factory() as session:
        result = await session.execute(text("""
            SELECT bt.id, bt.taisho_id, bt.cbeta_id, bt.title_zh, bt.title_en,
                   bt.title_sa, bt.title_bo, bt.title_pi, bt.translator,
                   bt.dynasty, bt.category, bt.subcategory, bt.fascicle_count,
                   bt.cbeta_url, bt.has_content, bt.lang,
                   ds.code as source_code
            FROM buddhist_texts bt
            LEFT JOIN data_sources ds ON bt.source_id = ds.id
        """))
        rows = result.fetchall()

    print(f"Found {len(rows)} texts in PostgreSQL")

    async def gen_actions():
        for row in rows:
            doc = {
                "id": row.id,
                "taisho_id": row.taisho_id,
                "cbeta_id": row.cbeta_id,
                "title_zh": row.title_zh,
                "title_en": row.title_en,
                "title_sa": row.title_sa,
                "title_bo": row.title_bo,
                "title_pi": row.title_pi,
                "translator": row.translator,
                "dynasty": row.dynasty,
                "category": row.category,
                "subcategory": row.subcategory,
                "fascicle_count": row.fascicle_count,
                "cbeta_url": row.cbeta_url,
                "has_content": row.has_content or False,
                "lang": row.lang or "lzh",
                "source_code": row.source_code,
            }
            # Remove None values
            doc = {k: v for k, v in doc.items() if v is not None}
            yield {
                "_index": INDEX_NAME,
                "_id": str(row.id),
                "_source": doc,
            }

    success, errors = await async_bulk(es, gen_actions(), chunk_size=500, raise_on_error=False)
    print(f"Elasticsearch: indexed {success} documents, {len(errors) if isinstance(errors, list) else errors} errors")

    # Verify count
    await es.indices.refresh(index=INDEX_NAME)
    count = await es.count(index=INDEX_NAME)
    print(f"ES index '{INDEX_NAME}' now has {count['count']} documents")

    await es.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
