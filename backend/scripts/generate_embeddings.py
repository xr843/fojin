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
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.source import DataSource
from app.models.text import BuddhistText, TextContent
from app.services.embedding import chunk_text, generate_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ensure_unique_index(session: AsyncSession) -> None:
    """Create unique index on (text_id, juan_num, chunk_index) if not exists."""
    await session.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_text_embeddings_chunk "
            "ON text_embeddings (text_id, juan_num, chunk_index)"
        )
    )
    await session.commit()


async def process_content(session: AsyncSession, tc: TextContent, progress: dict) -> int:
    """Process a single TextContent and store embeddings. Returns count of chunks."""
    chunks = chunk_text(tc.content, chunk_size=500, overlap=50)
    count = 0
    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 10:
            continue
        try:
            embedding = await generate_embedding(chunk)
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            await session.execute(
                text(
                    """
                    INSERT INTO text_embeddings (text_id, juan_num, chunk_index, chunk_text, embedding)
                    VALUES (:text_id, :juan_num, :chunk_index, :chunk_text, CAST(:embedding AS vector))
                    ON CONFLICT (text_id, juan_num, chunk_index) DO NOTHING
                    """
                ),
                {
                    "text_id": tc.text_id,
                    "juan_num": tc.juan_num,
                    "chunk_index": i,
                    "chunk_text": chunk,
                    "embedding": embedding_str,
                },
            )
            count += 1
        except Exception:
            logger.exception(f"Failed to embed chunk {i} of text {tc.text_id} juan {tc.juan_num}")
        progress["total"] += 1
        if progress["total"] % 100 == 0:
            logger.info(f"Progress: {progress['total']} chunks processed so far")
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

        progress = {"total": 0}
        for processed, tc in enumerate(contents, 1):
            count = await process_content(session, tc, progress)
            logger.info(
                f"[{processed}/{total}] text_id={tc.text_id} juan={tc.juan_num} "
                f"-> {count} chunks embedded"
            )
        logger.info(f"Done. Total chunks processed: {progress['total']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--text-id", type=int, default=None)
    parser.add_argument("--source", type=str, default=None, help="Filter by data source code (e.g. gretil)")
    args = parser.parse_args()
    asyncio.run(main(args.batch_size, args.text_id, args.source))
