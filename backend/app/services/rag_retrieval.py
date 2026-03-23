"""RAG retrieval: pgvector semantic similarity search."""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatSource
from app.services.embedding import generate_embedding, similarity_search

logger = logging.getLogger(__name__)

# Minimum cosine similarity score to include a chunk in RAG context.
# Chunks below this threshold are considered irrelevant and filtered out.
MIN_RELEVANCE_SCORE = 0.35


def _format_source_label(result: dict) -> str:
    if result.get("title_zh"):
        return f"《{result['title_zh']}》第{result['juan_num']}卷"
    return f"文本#{result['text_id']} 第{result['juan_num']}卷"


async def retrieve_rag_context(
    db: AsyncSession,
    query: str,
    *,
    prev_query: str | None = None,
    pgvector_limit: int = 10,
) -> tuple[list[ChatSource], str]:
    """Run pgvector similarity search and return (sources, context_text).

    Retrieves up to pgvector_limit candidates, then filters by relevance
    score and caps at 8 results. Gracefully degrades on failure.

    When prev_query is provided (from conversation history), it is prepended
    to the current query for embedding generation, enabling context-aware
    retrieval in multi-turn conversations.
    """
    sources: list[ChatSource] = []
    context_text = ""
    t0 = time.monotonic()

    try:
        search_query = f"{prev_query} {query}" if prev_query else query
        query_embedding = await generate_embedding(search_query)
        t1 = time.monotonic()
        logger.debug("TIMING: Embedding took %.2fs", t1 - t0)

        search_results = await similarity_search(db, query_embedding, limit=pgvector_limit)
        logger.debug("TIMING: pgvector search took %.2fs", time.monotonic() - t1)

        # Filter out low-relevance chunks and cap at 8
        search_results = [r for r in search_results if r["score"] >= MIN_RELEVANCE_SCORE][:8]

        sources = [ChatSource(**r) for r in search_results]
        context_parts = [f"[出处: {_format_source_label(r)}]\n{r['chunk_text']}" for r in search_results]
        context_text = "\n\n".join(context_parts)
    except Exception:
        logger.exception("Embedding/search failed, proceeding without RAG context")
        await db.rollback()

    logger.debug("TIMING: Total RAG retrieval took %.2fs (results: %d)", time.monotonic() - t0, len(sources))
    return sources, context_text
