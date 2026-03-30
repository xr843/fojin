"""RAG retrieval: pgvector semantic similarity search + reranking."""

import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.chat import ChatSource
from app.services.embedding import generate_embedding, similarity_search, source_similarity_search

logger = logging.getLogger(__name__)

# Minimum cosine similarity score to include a chunk in RAG context.
# Chunks below this threshold are considered irrelevant and filtered out.
MIN_RELEVANCE_SCORE = 0.35

# Maximum chunks to send to LLM after reranking (fewer but more relevant = better answers)
MAX_CONTEXT_CHUNKS = 5


def _format_source_label(result: dict) -> str:
    if result.get("title_zh"):
        return f"《{result['title_zh']}》第{result['juan_num']}卷"
    return f"文本#{result['text_id']} 第{result['juan_num']}卷"


def _keyword_rerank(query: str, results: list[dict]) -> list[dict]:
    """Re-score results using keyword overlap + vector similarity.

    Works without any external API (zero-config improvement).
    Combines:
      - Original vector cosine similarity (70% weight)
      - Character-level keyword overlap between query and chunk (20% weight)
      - Title match boost when query mentions a specific sutra name (10% weight)
    """
    query_chars = set(query)
    for r in results:
        chunk_chars = set(r["chunk_text"][:500])
        keyword_overlap = len(query_chars & chunk_chars) / max(len(query_chars), 1)

        # Title boost: check if any multi-char segment of the title appears in query
        title_boost = 0.0
        title = r.get("title_zh", "")
        if title:
            # Extract meaningful segments (2+ chars) from title for matching
            for i in range(len(title)):
                for length in range(2, min(len(title) - i + 1, 8)):
                    segment = title[i:i + length]
                    if segment in query:
                        title_boost = 1.0
                        break
                if title_boost > 0:
                    break

        original_score = r["score"]
        r["score"] = original_score * 0.7 + keyword_overlap * 0.2 + title_boost * 0.1
        logger.debug(
            "Rerank [keyword]: text_id=%s juan=%s | vec=%.3f kw=%.3f title=%.1f -> final=%.3f",
            r["text_id"], r["juan_num"], original_score, keyword_overlap, title_boost, r["score"],
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


async def _api_rerank(query: str, results: list[dict]) -> list[dict]:
    """Re-score results using an external cross-encoder reranker API.

    Uses the Jina/BAAI reranker API format (compatible with SiliconFlow, Jina, etc.).
    Falls back to keyword reranking on failure.
    """
    api_url = settings.reranker_api_url
    api_key = settings.reranker_api_key or settings.embedding_api_key or settings.llm_api_key
    model = settings.reranker_model

    documents = [r["chunk_text"][:500] for r in results]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{api_url}/rerank",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # API returns: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
        rerank_scores = {item["index"]: item["relevance_score"] for item in data["results"]}

        for i, r in enumerate(results):
            original_score = r["score"]
            api_score = rerank_scores.get(i, 0.0)
            # Blend: 40% vector similarity + 60% cross-encoder score
            r["score"] = original_score * 0.4 + api_score * 0.6
            logger.debug(
                "Rerank [API]: text_id=%s juan=%s | vec=%.3f api=%.3f -> final=%.3f",
                r["text_id"], r["juan_num"], original_score, api_score, r["score"],
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    except Exception:
        logger.warning("API reranker failed, falling back to keyword reranking", exc_info=True)
        return _keyword_rerank(query, results)


async def _rerank(query: str, results: list[dict]) -> list[dict]:
    """Rerank results using API cross-encoder if configured, else keyword-based."""
    if not results:
        return results

    t0 = time.monotonic()

    if settings.reranker_api_url:
        reranked = await _api_rerank(query, results)
        logger.debug("TIMING: API reranking took %.2fs (%d chunks)", time.monotonic() - t0, len(results))
    else:
        reranked = _keyword_rerank(query, results)
        logger.debug("TIMING: Keyword reranking took %.2fs (%d chunks)", time.monotonic() - t0, len(results))

    return reranked


async def retrieve_rag_context(
    db: AsyncSession,
    query: str,
    *,
    prev_query: str | None = None,
    pgvector_limit: int = 10,
) -> tuple[list[ChatSource], str]:
    """Run pgvector similarity search and return (sources, context_text).

    Pipeline:
      1. Embed query → pgvector HNSW top-K retrieval
      2. Filter by MIN_RELEVANCE_SCORE, dedupe by (text_id, juan_num)
      3. Rerank (keyword-based or API cross-encoder)
      4. Cap at MAX_CONTEXT_CHUNKS (5) results

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

        # Search text chunks, then data sources (sequential to avoid session conflicts)
        text_results = await similarity_search(db, query_embedding, limit=pgvector_limit)
        source_results = await source_similarity_search(db, query_embedding, limit=3, min_score=0.5)
        logger.debug("TIMING: pgvector search took %.2fs", time.monotonic() - t1)

        # Filter out low-relevance chunks and deduplicate by (text_id, juan_num)
        seen = set()
        filtered = []
        for r in text_results:
            if r["score"] < MIN_RELEVANCE_SCORE:
                continue
            key = (r["text_id"], r["juan_num"])
            if key in seen:
                continue
            seen.add(key)
            filtered.append(r)

        # Rerank filtered results
        reranked = await _rerank(query, filtered)

        # Cap at MAX_CONTEXT_CHUNKS (fewer but more relevant after reranking)
        search_results = reranked[:MAX_CONTEXT_CHUNKS]

        sources = [ChatSource(**r) for r in search_results]
        context_parts = [f"[出处: {_format_source_label(r)}]\n{r['chunk_text']}" for r in search_results]
        context_text = "\n\n".join(context_parts)

        # Append source recommendations if any matched
        if source_results:
            logger.debug("Found %d relevant data sources (scores: %s)",
                         len(source_results), [f"{s['name_zh']}={s['score']:.3f}" for s in source_results])
            source_lines = []
            for s in source_results:
                desc = (s["description"] or "")[:80]
                url = s["base_url"] or ""
                source_lines.append(f"- {s['name_zh']}：{desc}（{url}）")
            context_text += "\n\n[相关数据源推荐]\n" + "\n".join(source_lines)
    except Exception:
        logger.exception("Embedding/search failed, proceeding without RAG context")
        await db.rollback()

    logger.debug("TIMING: Total RAG retrieval took %.2fs (results: %d)", time.monotonic() - t0, len(sources))
    return sources, context_text
