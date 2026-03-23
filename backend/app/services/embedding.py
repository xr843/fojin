import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import EmbeddingServiceError

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
    """Call OpenAI-compatible API to generate embedding vector.

    Raises EmbeddingServiceError on network, HTTP, or response format errors.
    """
    try:
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
    except httpx.TimeoutException as exc:
        logger.warning("Embedding API timed out")
        raise EmbeddingServiceError("向量服务响应超时") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Embedding API returned HTTP %s", exc.response.status_code)
        raise EmbeddingServiceError(f"向量服务返回错误（HTTP {exc.response.status_code}）") from exc
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected embedding API response format: %s", exc)
        raise EmbeddingServiceError("向量服务返回格式异常") from exc
    except httpx.HTTPError as exc:
        logger.warning("Embedding API connection error: %s", exc)
        raise EmbeddingServiceError("向量服务连接失败") from exc


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single API call.

    OpenAI-compatible APIs accept a list of strings as `input`.
    Returns a list of embedding vectors in the same order as input.
    """
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{_embedding_api_url()}/embeddings",
                headers={"Authorization": f"Bearer {_embedding_api_key()}"},
                json={
                    "model": settings.embedding_model,
                    "input": texts,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # API returns embeddings sorted by index
            sorted_items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_items]
    except httpx.TimeoutException as exc:
        raise EmbeddingServiceError("向量服务响应超时") from exc
    except httpx.HTTPStatusError as exc:
        raise EmbeddingServiceError(f"向量服务返回错误（HTTP {exc.response.status_code}）") from exc
    except (KeyError, IndexError) as exc:
        raise EmbeddingServiceError("向量服务返回格式异常") from exc
    except httpx.HTTPError as exc:
        raise EmbeddingServiceError("向量服务连接失败") from exc


async def similarity_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 5,
) -> list[dict]:
    """Find most similar text chunks using pgvector cosine distance."""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    raw_conn = await session.connection()
    result = await raw_conn.exec_driver_sql(
        "SELECT te.text_id, te.juan_num, te.chunk_text, "
        "1 - (te.embedding <=> $1::vector) AS score, "
        "COALESCE(bt.title_zh, '') AS title_zh "
        "FROM text_embeddings te "
        "LEFT JOIN buddhist_texts bt ON bt.id = te.text_id "
        "WHERE te.embedding IS NOT NULL "
        "ORDER BY te.embedding <=> $1::vector "
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
            "title_zh": row[4],
        }
        for row in rows
    ]
