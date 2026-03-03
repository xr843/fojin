import logging

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


def _embedding_api_url() -> str:
    return settings.embedding_api_url or settings.llm_api_url


def _embedding_api_key() -> str:
    return settings.embedding_api_key or settings.llm_api_key


def chunk_text(content: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunks.append(content[start:end])
        start = end - overlap
    return chunks


async def generate_embedding(text_content: str) -> list[float]:
    """Call OpenAI-compatible API to generate embedding vector."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_embedding_api_url()}/embeddings",
            headers={"Authorization": f"Bearer {_embedding_api_key()}"},
            json={
                "model": settings.embedding_model,
                "input": text_content,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]


async def similarity_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 5,
) -> list[dict]:
    """Find most similar text chunks using pgvector cosine distance."""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    raw_conn = await session.connection()
    result = await raw_conn.exec_driver_sql(
        "SELECT text_id, juan_num, chunk_text, "
        "1 - (embedding <=> $1::vector) AS score "
        "FROM text_embeddings "
        "WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> $1::vector "
        "LIMIT $2",
        (embedding_str, limit),
    )
    rows = result.fetchall()
    return [
        {
            "text_id": row[0],
            "juan_num": row[1],
            "chunk_text": row[2],
            "score": float(row[3]),
        }
        for row in rows
    ]
