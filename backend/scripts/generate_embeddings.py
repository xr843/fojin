"""Batch generate embeddings for all text content.

Usage:
    python -m scripts.generate_embeddings [--batch-size 50] [--text-id 123] [--source gretil]
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.database import async_session
from app.models.source import DataSource
from app.models.text import BuddhistText, TextContent
from app.services.embedding import chunk_text, generate_embeddings_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 20  # chunks per API call


async def ensure_unique_index(session) -> None:
    await session.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_text_embeddings_chunk "
            "ON text_embeddings (text_id, juan_num, chunk_index)"
        )
    )
    await session.commit()


async def get_existing_chunks(session, text_id: int, juan_num: int) -> set[int]:
    """Return set of chunk_index values already in DB for this text+juan."""
    result = await session.execute(
        text("SELECT chunk_index FROM text_embeddings WHERE text_id = :tid AND juan_num = :jn"),
        {"tid": text_id, "jn": juan_num},
    )
    return {row[0] for row in result.fetchall()}


async def process_content(session, tc: TextContent, progress: dict) -> int:
    """Process a single TextContent using batch embedding. Returns new chunk count."""
    chunks = chunk_text(tc.content, chunk_size=500, overlap=50)

    # Skip chunks that already exist in DB
    existing = await get_existing_chunks(session, tc.text_id, tc.juan_num)
    new_chunks = [(i, c) for i, c in enumerate(chunks) if i not in existing and len(c.strip()) >= 10]

    if not new_chunks:
        progress["skipped"] += len(chunks)
        return 0

    count = 0
    # Process in batches of EMBED_BATCH_SIZE
    for batch_start in range(0, len(new_chunks), EMBED_BATCH_SIZE):
        batch = new_chunks[batch_start:batch_start + EMBED_BATCH_SIZE]
        batch_texts = [c for _, c in batch]

        try:
            embeddings = await generate_embeddings_batch(batch_texts)
        except Exception:
            logger.exception(f"Batch embedding failed for text {tc.text_id} juan {tc.juan_num}")
            progress["total"] += len(batch)
            continue

        for (chunk_idx, chunk_text_str), embedding in zip(batch, embeddings, strict=True):
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            await session.execute(
                text(
                    "INSERT INTO text_embeddings (text_id, juan_num, chunk_index, chunk_text, embedding) "
                    "VALUES (:text_id, :juan_num, :chunk_index, :chunk_text, CAST(:embedding AS vector)) "
                    "ON CONFLICT (text_id, juan_num, chunk_index) DO NOTHING"
                ),
                {
                    "text_id": tc.text_id,
                    "juan_num": tc.juan_num,
                    "chunk_index": chunk_idx,
                    "chunk_text": chunk_text_str,
                    "embedding": embedding_str,
                },
            )
            count += 1

        progress["total"] += len(batch)
        if progress["total"] % 100 == 0:
            logger.info(f"Progress: {progress['total']} new chunks processed")

    await session.commit()
    return count


async def main(batch_size: int, text_id: int | None, source: str | None = None) -> None:
    async with async_session() as session:
        await ensure_unique_index(session)

        query = select(TextContent)
        if text_id:
            query = query.where(TextContent.text_id == text_id)
        if source:
            subq = select(BuddhistText.id).join(DataSource, BuddhistText.source_id == DataSource.id).where(
                DataSource.code == source
            )
            query = query.where(TextContent.text_id.in_(subq))
        query = query.order_by(TextContent.text_id, TextContent.juan_num)

        result = await session.execute(query)
        contents = result.scalars().all()
        total = len(contents)
        logger.info(f"Found {total} text content records to process")

        progress = {"total": 0, "skipped": 0}
        for processed, tc in enumerate(contents, 1):
            count = await process_content(session, tc, progress)
            if count > 0:
                logger.info(
                    f"[{processed}/{total}] text_id={tc.text_id} juan={tc.juan_num} "
                    f"-> {count} new chunks embedded"
                )
            elif processed % 50 == 0:
                logger.info(f"[{processed}/{total}] skipping (already embedded)")
        logger.info(f"Done. New chunks: {progress['total']}, Skipped: {progress['skipped']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--text-id", type=int, default=None)
    parser.add_argument("--source", type=str, default=None, help="Filter by data source code (e.g. gretil)")
    args = parser.parse_args()
    asyncio.run(main(args.batch_size, args.text_id, args.source))
