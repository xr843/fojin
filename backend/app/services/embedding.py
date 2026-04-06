import hashlib
import logging
from collections import OrderedDict

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import EmbeddingServiceError

logger = logging.getLogger(__name__)

# In-process LRU cache for query embeddings (avoids repeated API calls for identical queries)
_EMBEDDING_CACHE_MAX = 256
_embedding_cache: OrderedDict[str, list[float]] = OrderedDict()


def _embedding_api_url() -> str:
    return settings.embedding_api_url or settings.llm_api_url


def _embedding_api_key() -> str:
    return settings.embedding_api_key or settings.llm_api_key


def chunk_text(content: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    if not content:
        return []
    if overlap >= chunk_size:
        overlap = 0
    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunks.append(content[start:end])
        start = end - overlap
    return chunks


async def generate_embedding(text_content: str) -> list[float]:
    """Call OpenAI-compatible API to generate embedding vector.

    Uses an in-process LRU cache to avoid repeated API calls for identical queries.
    Raises EmbeddingServiceError on network, HTTP, or response format errors.
    """
    cache_key = hashlib.md5(text_content.encode(), usedforsecurity=False).hexdigest()  # nosec B324
    if cache_key in _embedding_cache:
        _embedding_cache.move_to_end(cache_key)
        logger.debug("Embedding cache hit for query (md5=%s)", cache_key[:8])
        return _embedding_cache[cache_key]

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
            embedding = data["data"][0]["embedding"]
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

    # Cache the result
    _embedding_cache[cache_key] = embedding
    if len(_embedding_cache) > _EMBEDDING_CACHE_MAX:
        _embedding_cache.popitem(last=False)
    return embedding


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
    scope_text_ids: list[int] | None = None,
) -> list[dict]:
    """Find most similar text chunks using pgvector cosine distance.

    When scope_text_ids is provided, only search within those texts
    (used for master persona mode to restrict RAG to the master's core scriptures).
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    raw_conn = await session.connection()
    if scope_text_ids:
        placeholders = ",".join(str(tid) for tid in scope_text_ids)
        result = await raw_conn.exec_driver_sql(
            "SELECT te.text_id, te.juan_num, te.chunk_text, "
            "1 - (te.embedding <=> $1::vector) AS score, "
            "COALESCE(bt.title_zh, '') AS title_zh "
            "FROM text_embeddings te "
            "LEFT JOIN buddhist_texts bt ON bt.id = te.text_id "
            f"WHERE te.embedding IS NOT NULL AND te.text_id IN ({placeholders}) "  # nosec B608 — IDs from hardcoded MasterProfile, not user input
            "ORDER BY te.embedding <=> $1::vector "
            "LIMIT $2",
            (embedding_str, limit),
        )
    else:
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


async def source_similarity_search(
    session: AsyncSession,
    query_embedding: list[float],
    limit: int = 3,
    min_score: float = 0.5,
) -> list[dict]:
    """Find most relevant data sources using pgvector cosine distance."""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    raw_conn = await session.connection()
    result = await raw_conn.exec_driver_sql(
        "SELECT ds.id, ds.code, ds.name_zh, ds.description, ds.base_url, "
        "1 - (ds.embedding <=> $1::vector) AS score "
        "FROM data_sources ds "
        "WHERE ds.embedding IS NOT NULL AND ds.is_active = true "
        "ORDER BY ds.embedding <=> $1::vector "
        "LIMIT $2",
        (embedding_str, limit),
    )
    rows = result.fetchall()
    return [
        {
            "source_id": row[0],
            "code": row[1],
            "name_zh": row[2],
            "description": row[3],
            "base_url": row[4],
            "score": float(row[5]),
        }
        for row in rows
        if float(row[5]) >= min_score
    ]
