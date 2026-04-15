"""RAG retrieval: pgvector semantic similarity search + reranking."""

import logging
import re
import time

import httpx
from opencc import OpenCC
from sqlalchemy import or_, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.models.dictionary import DictionaryEntry
from app.schemas.chat import ChatSource
from app.services.embedding import generate_embedding, similarity_search, source_similarity_search

logger = logging.getLogger(__name__)

# Minimum cosine similarity score to include a chunk in RAG context.
# Chunks below this threshold are considered irrelevant and filtered out.
MIN_RELEVANCE_SCORE = 0.35

# Maximum chunks to send to LLM after reranking (fewer but more relevant = better answers)
MAX_CONTEXT_CHUNKS = 5

# Trilingual RAG: enable per-language retrieval + alignment-aware merging.
# When True, retrieve_rag_context fetches separately from lzh/pi/bo and then
# attaches parallel_chunks to primary hits via alignment_pairs lookup.
# Controlled by env var so it can be disabled in one place if needed.
ENABLE_PARALLEL_RAG = settings.enable_parallel_rag if hasattr(settings, "enable_parallel_rag") else True

# Per-lang top-k budgets for parallel mode. Total retrieved = LZH_K + PI_K + BO_K.
# Keep larger for lzh since 95%+ users read Chinese and primary narrative stays in lzh.
PARALLEL_LZH_K = 8
PARALLEL_PI_K = 4
PARALLEL_BO_K = 4


def _format_source_label(result: dict) -> str:
    if result.get("title_zh"):
        return f"《{result['title_zh']}》第{result['juan_num']}卷"
    return f"文本#{result['text_id']} 第{result['juan_num']}卷"


def _merge_with_alignment_sync(lzh_hits: list[dict], pi_hits: list[dict], bo_hits: list[dict]) -> list[dict]:
    """Merge per-language RAG hits into a single score-ranked list.

    Called in place of a single similarity_search when ENABLE_PARALLEL_RAG is on.
    Primary source (highest-ranked lzh) is preserved; pi/bo hits are interleaved
    by score so the LLM gets a cross-canon sampling. Alignment parallels are
    attached later in _attach_parallel_chunks, not here — keeps responsibilities
    separated.
    """
    merged: list[dict] = []
    merged.extend(lzh_hits)
    merged.extend(pi_hits)
    merged.extend(bo_hits)
    merged.sort(key=lambda r: r["score"], reverse=True)
    return merged


async def _attach_parallel_chunks(db: AsyncSession, results: list[dict]) -> None:
    """For each result in-place, populate its parallel_chunks via alignment_pairs.

    Looks up alignment_pairs for the (text_id, juan_num, chunk_index) tuple in
    both directions (text_a and text_b sides). For each match, fetches the
    aligned chunk's text from text_embeddings + title_zh from buddhist_texts.

    Modifies `results` in place by setting result["parallel_chunks"] to a list
    of ParallelChunk-compatible dicts.
    """
    if not results:
        return
    # Build a bulk query: "for any of these (text_id, juan, chunk) tuples, find
    # alignment_pairs where text_a_* OR text_b_* matches, and return the other side"
    for r in results:
        r.setdefault("parallel_chunks", [])
    try:
        for r in results:
            tid = r["text_id"]
            juan = r["juan_num"]
            cidx = r["chunk_index"]
            sql = sql_text("""
                SELECT
                    CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                         THEN ap.text_b_id ELSE ap.text_a_id END AS other_text_id,
                    CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                         THEN ap.text_b_juan_num ELSE ap.text_a_juan_num END AS other_juan,
                    CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                         THEN ap.text_b_chunk_index ELSE ap.text_a_chunk_index END AS other_chunk_idx,
                    CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                         THEN ap.text_b_lang ELSE ap.text_a_lang END AS other_lang,
                    ap.confidence
                FROM alignment_pairs ap
                WHERE (
                    (ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx)
                    OR
                    (ap.text_b_id = :tid AND ap.text_b_juan_num = :juan AND ap.text_b_chunk_index = :cidx)
                )
                AND ap.text_a_chunk_index IS NOT NULL
                ORDER BY ap.confidence DESC
                LIMIT 5
            """)
            rows = (await db.execute(sql, {"tid": tid, "juan": juan, "cidx": cidx})).fetchall()
            if not rows:
                continue
            # Fetch chunk_text + title for each parallel. Loop-per-row is fine
            # for the expected small N (≤ 5 parallels × 5 primary results).
            parallel_keys = [(row[0], row[1], row[2], row[3], float(row[4])) for row in rows]
            text_map: dict[tuple[int, int, int], tuple[str, str]] = {}
            for other_tid, other_juan, other_cidx, _lang, _conf in parallel_keys:
                text_row = (await db.execute(
                    sql_text(
                        "SELECT te.chunk_text, "
                        "COALESCE(bt.title_zh, bt.title_sa, bt.title_pi, bt.title_en, '') "
                        "FROM text_embeddings te "
                        "LEFT JOIN buddhist_texts bt ON bt.id = te.text_id "
                        "WHERE te.text_id = :tid AND te.juan_num = :juan AND te.chunk_index = :cidx"
                    ),
                    {"tid": other_tid, "juan": other_juan, "cidx": other_cidx},
                )).fetchone()
                if text_row:
                    text_map[(other_tid, other_juan, other_cidx)] = (text_row[0], text_row[1])
            for other_tid, other_juan, other_cidx, other_lang, conf in parallel_keys:
                key = (other_tid, other_juan, other_cidx)
                if key not in text_map:
                    continue
                chunk_text, title = text_map[key]
                r["parallel_chunks"].append({
                    "text_id": other_tid,
                    "juan_num": other_juan,
                    "chunk_index": other_cidx,
                    "chunk_text": chunk_text,
                    "lang": other_lang or "lzh",
                    "title": title,
                    "confidence": conf,
                })
    except Exception:
        logger.exception("Failed to attach parallel chunks")


def _format_context_block(result: dict) -> str:
    """Format a single RAG result into the LLM context string.

    Adds [跨藏对读] annotations when parallel_chunks are present, so the LLM
    knows it has cross-canon evidence available for the citation.
    """
    header = f"[出处: {_format_source_label(result)}]"
    body = result["chunk_text"]
    parallels = result.get("parallel_chunks") or []
    if parallels:
        parallel_lines = []
        for p in parallels[:3]:  # cap at 3 parallels per primary source
            lang_label = {"pi": "巴利", "bo": "藏", "sa": "梵", "en": "英", "lzh": "汉"}.get(p["lang"], p["lang"])
            title = p.get("title", "") or "其他藏经"
            parallel_lines.append(
                f"  · [{lang_label}] 《{title}》 第{p['juan_num']}卷: {p['chunk_text'][:300]}"
            )
        parallel_block = "\n[跨藏对读 parallel_chunks]\n" + "\n".join(parallel_lines)
        return f"{header}\n{body}{parallel_block}"
    return f"{header}\n{body}"


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


_s2t = OpenCC("s2t")
_t2s = OpenCC("t2s")

# Maximum dictionary definitions to include in RAG context
MAX_DICT_ENTRIES = 3
# Maximum characters per dictionary definition
MAX_DICT_DEF_CHARS = 200

# Pattern to extract CJK terms (2-8 chars) from user message
_CJK_TERM_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]{2,8}")
# Common question words to strip before extracting terms
_QUESTION_WORDS = re.compile(
    r"什么是|是什么|什么叫|什么意思|怎么理解|如何理解|何谓|何为|"
    r"请问|请解释|解释一下|介绍一下|简述|详解|含义|意思|概念|定义|"
    r"的意思|是指|指的是|讲的是|说的是"
)


def _zh_variants(q: str) -> list[str]:
    """Return deduplicated [original, simplified, traditional] variants."""
    return list({q, _t2s.convert(q), _s2t.convert(q)})


async def _lookup_dictionary_terms(db: AsyncSession, query: str) -> str:
    """Look up Buddhist dictionary entries matching terms in the user query.

    Extracts CJK terms from the query and searches for exact headword matches,
    falling back to prefix matches. Returns formatted text block or empty string.
    """
    # Strip common question words to isolate the actual term
    cleaned = _QUESTION_WORDS.sub("", query).strip()
    # Extract candidate terms from cleaned query (CJK sequences of 2-8 chars)
    terms = _CJK_TERM_RE.findall(cleaned)
    # Also try the original query as fallback
    if not terms:
        terms = _CJK_TERM_RE.findall(query)
    if not terms:
        return ""

    # Deduplicate while preserving order, limit to first 5 terms
    seen: set[str] = set()
    unique_terms: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
        if len(unique_terms) >= 5:
            break

    # Collect all variants for all terms
    all_variants: list[str] = []
    for term in unique_terms:
        all_variants.extend(_zh_variants(term))
    all_variants = list(set(all_variants))

    try:
        # Phase 1: exact headword match
        exact_conds = [DictionaryEntry.headword == v for v in all_variants]
        stmt = (
            select(DictionaryEntry)
            .where(or_(*exact_conds))
            .options(joinedload(DictionaryEntry.source))
            .limit(MAX_DICT_ENTRIES)
        )
        result = await db.execute(stmt)
        entries = list(result.unique().scalars().all())

        # Phase 2: prefix match if exact found too few
        if len(entries) < MAX_DICT_ENTRIES:
            prefix_conds = [DictionaryEntry.headword.startswith(v) for v in all_variants]
            seen_ids = {e.id for e in entries}
            stmt2 = (
                select(DictionaryEntry)
                .where(or_(*prefix_conds))
                .options(joinedload(DictionaryEntry.source))
                .limit(MAX_DICT_ENTRIES)
            )
            result2 = await db.execute(stmt2)
            for e in result2.unique().scalars().all():
                if e.id not in seen_ids and len(entries) < MAX_DICT_ENTRIES:
                    entries.append(e)
                    seen_ids.add(e.id)

        if not entries:
            return ""

        # Format dictionary entries
        lines: list[str] = []
        for e in entries:
            source_name = e.source.name_zh if e.source else "未知辞典"
            definition = (e.definition or "")[:MAX_DICT_DEF_CHARS]
            if e.definition and len(e.definition) > MAX_DICT_DEF_CHARS:
                definition += "…"
            lines.append(f"「{e.headword}」—— {source_name}：{definition}")

        return "【辞典参考】\n" + "\n".join(lines)

    except Exception:
        logger.warning("Dictionary lookup failed, skipping", exc_info=True)
        return ""


async def retrieve_rag_context(
    db: AsyncSession,
    query: str,
    *,
    prev_query: str | None = None,
    pgvector_limit: int = 10,
    scope_text_ids: list[int] | None = None,
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

        # Text chunk retrieval: two modes depending on ENABLE_PARALLEL_RAG
        if ENABLE_PARALLEL_RAG and not scope_text_ids:
            # Per-language top-k retrieval, then alignment-aware merging.
            # scope_text_ids (master persona mode) bypasses parallel mode
            # since master's scriptures are already filtered to a specific set.
            lzh_hits = await similarity_search(db, query_embedding, limit=PARALLEL_LZH_K, lang_list=["lzh"])
            pi_hits = await similarity_search(db, query_embedding, limit=PARALLEL_PI_K, lang_list=["pi"])
            bo_hits = await similarity_search(db, query_embedding, limit=PARALLEL_BO_K, lang_list=["bo"])
            text_results = _merge_with_alignment_sync(lzh_hits, pi_hits, bo_hits)
        else:
            text_results = await similarity_search(db, query_embedding, limit=pgvector_limit, scope_text_ids=scope_text_ids)

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

        # Attach alignment parallels to sources (only if parallel mode on).
        # Query alignment_pairs for each primary hit; if found, inject the
        # aligned chunks' text into parallel_chunks for downstream use.
        if ENABLE_PARALLEL_RAG and search_results:
            await _attach_parallel_chunks(db, search_results)

        sources = [ChatSource(**{k: v for k, v in r.items() if k not in ("source_id",)} | {"source_id": r.get("source_id")}) for r in search_results]
        context_parts = [_format_context_block(r) for r in search_results]
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

        # Dictionary term lookup for authoritative definitions
        t_dict = time.monotonic()
        dict_text = await _lookup_dictionary_terms(db, query)
        if dict_text:
            context_text += "\n\n" + dict_text
            logger.debug("TIMING: Dictionary lookup took %.2fs", time.monotonic() - t_dict)
    except Exception:
        logger.exception("Embedding/search failed, proceeding without RAG context")
        await db.rollback()

    logger.debug("TIMING: Total RAG retrieval took %.2fs (results: %d)", time.monotonic() - t0, len(sources))
    return sources, context_text
