import logging
from collections import defaultdict

from elasticsearch import AsyncElasticsearch
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import CONTENT_INDEX_NAME, INDEX_NAME
from app.models.relation import TextRelation
from app.models.text import BuddhistText
from app.schemas.text import (
    CrossLanguageSearchHit,
    CrossLanguageSearchResponse,
    RelatedTranslation,
    SearchHit,
    SearchResponse,
    SemanticSearchHit,
    SemanticSearchResponse,
)
from app.services.embedding import generate_embedding
from app.services.rag_retrieval import MIN_RELEVANCE_SCORE

logger = logging.getLogger(__name__)


# Language code to primary title field mapping
_LANG_TITLE_MAP = {
    "lzh": "title_zh", "zh": "title_zh",
    "en": "title_en",
    "sa": "title_sa",
    "pi": "title_pi",
    "bo": "title_bo",
}


async def fetch_related_translations(
    db: AsyncSession,
    text_ids: list[int],
) -> dict[int, list[RelatedTranslation]]:
    """Batch-fetch related translations for a list of text IDs.

    Returns a dict mapping text_id -> list of RelatedTranslation.
    Only includes parallel and alt_translation relations.
    """
    if not text_ids:
        return {}

    # Query text_relations for all text_ids at once
    stmt = (
        select(TextRelation)
        .where(
            or_(
                TextRelation.text_a_id.in_(text_ids),
                TextRelation.text_b_id.in_(text_ids),
            ),
            TextRelation.relation_type.in_(["parallel", "alt_translation"]),
        )
    )
    result = await db.execute(stmt)
    relations = result.scalars().all()

    if not relations:
        return {}

    # Collect all related text IDs we need metadata for
    related_ids: set[int] = set()
    for rel in relations:
        related_ids.add(rel.text_a_id)
        related_ids.add(rel.text_b_id)
    # Fetch metadata for all related texts (including those in text_ids,
    # so cross-references between search results are preserved)
    meta_stmt = (
        select(
            BuddhistText.id,
            BuddhistText.title_zh,
            BuddhistText.title_en,
            BuddhistText.title_sa,
            BuddhistText.title_pi,
            BuddhistText.title_bo,
            BuddhistText.lang,
        )
        .where(BuddhistText.id.in_(related_ids))
    )
    meta_result = await db.execute(meta_stmt)
    meta_map: dict[int, dict] = {}
    for row in meta_result.all():
        meta_map[row.id] = {
            "id": row.id,
            "title_zh": row.title_zh,
            "title_en": row.title_en,
            "title_sa": row.title_sa,
            "title_pi": row.title_pi,
            "title_bo": row.title_bo,
            "lang": row.lang,
        }

    # Build the result mapping
    result_map: dict[int, list[RelatedTranslation]] = defaultdict(list)
    seen: dict[int, set[int]] = defaultdict(set)  # prevent duplicates

    for rel in relations:
        for tid in text_ids:
            if rel.text_a_id == tid:
                other_id = rel.text_b_id
            elif rel.text_b_id == tid:
                other_id = rel.text_a_id
            else:
                continue

            if other_id in seen[tid]:
                continue
            seen[tid].add(other_id)

            meta = meta_map.get(other_id)
            if not meta:
                continue

            # Pick the best title for the related text
            lang = meta["lang"]
            title_field = _LANG_TITLE_MAP.get(lang, "title_zh")
            title = meta.get(title_field) or meta.get("title_zh") or ""

            result_map[tid].append(
                RelatedTranslation(
                    id=other_id,
                    title=title,
                    lang=lang,
                    relation_type=rel.relation_type,
                )
            )

    return dict(result_map)


async def search_texts(
    es: AsyncElasticsearch,
    query: str,
    page: int = 1,
    size: int = 20,
    dynasty: str | None = None,
    category: str | None = None,
    lang: str | None = None,
    sources: str | None = None,
    sort: str | None = None,
    db: AsyncSession | None = None,
) -> SearchResponse:
    """Search Buddhist texts in Elasticsearch."""
    must = []
    filter_clauses = []

    if query:
        must.append(
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title_zh^3",
                        "title_en^2",
                        "title_sa^2",
                        "title_bo",
                        "title_pi",
                        "translator^2",
                        "cbeta_id^4",
                        "taisho_id^4",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        )
    else:
        must.append({"match_all": {}})

    if dynasty:
        filter_clauses.append({"term": {"dynasty": dynasty}})
    if category:
        filter_clauses.append({"term": {"category": category}})
    if lang:
        filter_clauses.append({"term": {"lang": lang}})
    if sources:
        codes = [c.strip() for c in sources.split(",") if c.strip()]
        if len(codes) == 1:
            filter_clauses.append({"term": {"source_code": codes[0]}})
        elif codes:
            filter_clauses.append({"terms": {"source_code": codes}})

    sort_clause = []
    if sort == "title":
        sort_clause = [{"title_zh.keyword": "asc"}, "_score"]
    elif sort == "dynasty":
        sort_clause = [{"dynasty.keyword": "asc"}, "_score"]
    elif sort != "relevance":
        # Default: relevance (use ES default _score sorting)
        pass

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filter_clauses,
            }
        },
        "highlight": {
            "fields": {
                "title_zh": {},
                "title_en": {},
                "translator": {},
            },
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
        "from": (page - 1) * size,
        "size": size,
    }

    if sort_clause:
        body["sort"] = sort_clause

    result = await es.search(index=INDEX_NAME, body=body, timeout="10s")

    hits = result["hits"]
    total = hits["total"]["value"]

    results = []
    for hit in hits["hits"]:
        src = hit["_source"]
        results.append(
            SearchHit(
                id=src.get("id") or int(hit["_id"]),
                taisho_id=src.get("taisho_id"),
                cbeta_id=src["cbeta_id"],
                title_zh=src["title_zh"],
                translator=src.get("translator"),
                dynasty=src.get("dynasty"),
                category=src.get("category"),
                cbeta_url=src.get("cbeta_url"),
                has_content=src.get("has_content", False),
                source_code=src.get("source_code"),
                score=hit["_score"],
                highlight=hit.get("highlight"),
            )
        )

    # When results are few, try to provide a spelling/phrase suggestion
    suggestion = None
    if query and total < 3:
        suggestion = await _get_phrase_suggestion(es, query)

    # Enrich with related translations if db session is available
    if db and results:
        text_ids = [r.id for r in results]
        rel_map = await fetch_related_translations(db, text_ids)
        for r in results:
            r.related_translations = rel_map.get(r.id, [])

    return SearchResponse(total=total, page=page, size=size, results=results, suggestion=suggestion)


async def search_content(
    es: AsyncElasticsearch,
    query: str,
    page: int = 1,
    size: int = 20,
    sources: str | None = None,
    lang: str | None = None,
) -> dict:
    """Search full-text content in Elasticsearch."""
    if not query:
        return {"total": 0, "page": page, "size": size, "results": []}

    content_query: dict = {
        "match": {
            "content": {
                "query": query,
                "analyzer": "cjk_content",
            }
        }
    }

    # Wrap in bool query if sources or lang filter is present
    filter_clauses = []
    if sources:
        codes = [c.strip() for c in sources.split(",") if c.strip()]
        if codes:
            filter_clauses.append({"term": {"source_code": codes[0]}} if len(codes) == 1 else {"terms": {"source_code": codes}})
    if lang:
        filter_clauses.append({"term": {"lang": lang}})

    if filter_clauses:
        content_query = {
            "bool": {
                "must": [content_query],
                "filter": filter_clauses,
            }
        }

    highlight_cfg = {
        "fields": {
            "content": {
                "fragment_size": 120,
                "number_of_fragments": 3,
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            }
        }
    }

    # Collapse by text_id: one result per work, with inner_hits for juan count
    body = {
        "query": content_query,
        "highlight": highlight_cfg,
        "collapse": {
            "field": "text_id",
            "inner_hits": {
                "name": "matched_juans",
                "size": 5,
                "sort": [{"_score": "desc"}],
                "highlight": highlight_cfg,
            },
        },
        "from": (page - 1) * size,
        "size": size,
    }

    # Use a separate cardinality aggregation to get total unique works
    body["aggs"] = {
        "total_works": {"cardinality": {"field": "text_id"}},
        "total_juans": {"value_count": {"field": "text_id"}},
    }

    result = await es.search(index=CONTENT_INDEX_NAME, body=body, timeout="10s")
    hits = result["hits"]
    total_works = result.get("aggregations", {}).get("total_works", {}).get("value", 0)
    total_juans = result.get("aggregations", {}).get("total_juans", {}).get("value", 0)

    results = []
    for hit in hits["hits"]:
        src = hit["_source"]
        # inner_hits contains all matched juans for this work
        inner = hit.get("inner_hits", {}).get("matched_juans", {})
        inner_total = inner.get("hits", {}).get("total", {}).get("value", 1)
        inner_hits = inner.get("hits", {}).get("hits", [])

        matched_juans = []
        for ih in inner_hits:
            ih_src = ih["_source"]
            matched_juans.append({
                "juan_num": ih_src.get("juan_num", 1),
                "highlight": ih.get("highlight", {}).get("content", []),
                "score": ih["_score"],
            })

        results.append({
            "text_id": src["text_id"],
            "cbeta_id": src.get("cbeta_id", ""),
            "title_zh": src.get("title_zh", ""),
            "translator": src.get("translator"),
            "dynasty": src.get("dynasty"),
            "juan_num": src.get("juan_num", 1),
            "lang": src.get("lang", "lzh"),
            "source_code": src.get("source_code"),
            "highlight": hit.get("highlight", {}).get("content", []),
            "score": hit["_score"],
            "matched_juan_count": inner_total,
            "matched_juans": matched_juans,
        })

    return {
        "total": total_works,
        "total_juans": total_juans,
        "page": page,
        "size": size,
        "results": results,
    }


async def _get_phrase_suggestion(es: AsyncElasticsearch, query: str) -> str | None:
    """Use ES phrase suggester to get a spelling correction for the query."""
    try:
        body = {
            "suggest": {
                "title_zh_suggestion": {
                    "text": query,
                    "phrase": {
                        "field": "title_zh",
                        "size": 1,
                        "gram_size": 2,
                        "direct_generator": [{"field": "title_zh", "suggest_mode": "popular"}],
                        "highlight": {"pre_tag": "", "post_tag": ""},
                    },
                },
                "title_en_suggestion": {
                    "text": query,
                    "phrase": {
                        "field": "title_en",
                        "size": 1,
                        "gram_size": 3,
                        "direct_generator": [{"field": "title_en", "suggest_mode": "popular"}],
                        "highlight": {"pre_tag": "", "post_tag": ""},
                    },
                },
            },
            "size": 0,
        }
        result = await es.search(index=INDEX_NAME, body=body, timeout="5s")
        suggestions = result.get("suggest", {})

        # Check title_zh first, then title_en
        for key in ("title_zh_suggestion", "title_en_suggestion"):
            options = suggestions.get(key, [{}])[0].get("options", []) if suggestions.get(key) else []
            if options and options[0].get("text") and options[0]["text"].strip() != query.strip():
                return options[0]["text"]
        return None
    except Exception:
        logger.debug("Phrase suggestion failed for query=%s", query, exc_info=True)
        return None


async def get_suggestions(es: AsyncElasticsearch, query: str, size: int = 5) -> list[str]:
    """Get autocomplete suggestions using match_phrase_prefix on title fields."""
    try:
        body = {
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        {"match_phrase_prefix": {"title_zh": {"query": query, "max_expansions": 20}}},
                        {"match_phrase_prefix": {"title_en": {"query": query, "max_expansions": 20}}},
                        {"match_phrase_prefix": {"translator": {"query": query, "max_expansions": 10}}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "_source": ["title_zh", "title_en"],
        }
        result = await es.search(index=INDEX_NAME, body=body, timeout="5s")
        hits = result["hits"]["hits"]

        seen: set[str] = set()
        suggestions: list[str] = []
        for hit in hits:
            src = hit["_source"]
            title = src.get("title_zh", "")
            if title and title not in seen:
                seen.add(title)
                suggestions.append(title)
        return suggestions[:size]
    except Exception:
        logger.debug("Autocomplete suggestions failed for query=%s", query, exc_info=True)
        return []


async def search_cross_language(
    es: AsyncElasticsearch,
    query: str,
    page: int = 1,
    size: int = 20,
    dynasty: str | None = None,
    category: str | None = None,
    sources: str | None = None,
    db: AsyncSession | None = None,
) -> CrossLanguageSearchResponse:
    """Cross-language search: search across ALL title fields simultaneously.

    For each result, fetches related translations and groups them together.
    """
    must = []
    filter_clauses: list[dict] = []

    if query:
        must.append(
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title_zh^3",
                        "title_en^2",
                        "title_sa^2",
                        "title_bo^2",
                        "title_pi^2",
                        "translator^1",
                        "cbeta_id^4",
                        "taisho_id^4",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        )
    else:
        must.append({"match_all": {}})

    if dynasty:
        filter_clauses.append({"term": {"dynasty": dynasty}})
    if category:
        filter_clauses.append({"term": {"category": category}})
    if sources:
        codes = [c.strip() for c in sources.split(",") if c.strip()]
        if len(codes) == 1:
            filter_clauses.append({"term": {"source_code": codes[0]}})
        elif codes:
            filter_clauses.append({"terms": {"source_code": codes}})

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filter_clauses,
            }
        },
        "highlight": {
            "fields": {
                "title_zh": {},
                "title_en": {},
                "title_sa": {},
                "title_pi": {},
                "title_bo": {},
                "translator": {},
            },
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
        "from": (page - 1) * size,
        "size": size,
    }

    result = await es.search(index=INDEX_NAME, body=body, timeout="10s")

    hits = result["hits"]
    total = hits["total"]["value"]

    results = []
    for hit in hits["hits"]:
        src = hit["_source"]
        results.append(
            CrossLanguageSearchHit(
                id=src.get("id") or int(hit["_id"]),
                taisho_id=src.get("taisho_id"),
                cbeta_id=src["cbeta_id"],
                title_zh=src["title_zh"],
                title_en=src.get("title_en"),
                title_sa=src.get("title_sa"),
                title_pi=src.get("title_pi"),
                title_bo=src.get("title_bo"),
                translator=src.get("translator"),
                dynasty=src.get("dynasty"),
                category=src.get("category"),
                cbeta_url=src.get("cbeta_url"),
                has_content=src.get("has_content", False),
                source_code=src.get("source_code"),
                lang=src.get("lang", "lzh"),
                score=hit["_score"],
                highlight=hit.get("highlight"),
            )
        )

    # Enrich with related translations
    if db and results:
        text_ids = [r.id for r in results]
        rel_map = await fetch_related_translations(db, text_ids)
        for r in results:
            r.related_translations = rel_map.get(r.id, [])

    suggestion = None
    if query and total < 3:
        suggestion = await _get_phrase_suggestion(es, query)

    return CrossLanguageSearchResponse(
        total=total, page=page, size=size, results=results, suggestion=suggestion,
    )


async def get_aggregations(es: AsyncElasticsearch) -> dict:
    """Get filter aggregations (dynasties, categories, languages, sources)."""
    body = {
        "size": 0,
        "aggs": {
            "dynasties": {"terms": {"field": "dynasty", "size": 50}},
            "categories": {"terms": {"field": "category", "size": 50}},
            "languages": {"terms": {"field": "lang", "size": 20}},
            "sources": {"terms": {"field": "source_code", "size": 30}},
        },
    }
    result = await es.search(index=INDEX_NAME, body=body, timeout="10s")
    aggs = result["aggregations"]
    return {
        "dynasties": [b["key"] for b in aggs["dynasties"]["buckets"]],
        "categories": [b["key"] for b in aggs["categories"]["buckets"]],
        "languages": [b["key"] for b in aggs["languages"]["buckets"]],
        "sources": [b["key"] for b in aggs["sources"]["buckets"]],
    }


async def search_semantic(
    db: AsyncSession,
    query: str,
    size: int = 20,
    dynasty: str | None = None,
    category: str | None = None,
    lang: str | None = None,
    sources: str | None = None,
) -> SemanticSearchResponse:
    """语义搜索：基于 pgvector 向量检索，复用 RAG embedding 能力。

    流程：
      1. 生成查询向量
      2. pgvector 余弦相似度检索（多取一些用于后过滤）
      3. 关联 buddhist_texts 获取元数据
      4. 按筛选条件后过滤
      5. 去重（同一 text_id 只保留最高分的 chunk）
      6. 截断至 size 条返回
    """
    if not query:
        return SemanticSearchResponse(total=0, results=[])

    try:
        query_embedding = await generate_embedding(query)
    except Exception:
        logger.exception("语义搜索：生成向量失败")
        return SemanticSearchResponse(total=0, results=[], error="向量服务暂时不可用，请稍后重试")

    # 多取一些结果用于后过滤（筛选条件可能过滤掉一部分）
    pgvector_limit = size * 5

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # 构建筛选条件 SQL
    filter_conditions = []
    params: list = [embedding_str, MIN_RELEVANCE_SCORE, pgvector_limit]
    param_idx = 4  # $1=embedding, $2=min_score, $3=limit, $4+ 为筛选参数

    if dynasty:
        filter_conditions.append(f"AND bt.dynasty = ${param_idx}")
        params.append(dynasty)
        param_idx += 1
    if category:
        filter_conditions.append(f"AND bt.category = ${param_idx}")
        params.append(category)
        param_idx += 1
    if lang:
        filter_conditions.append(f"AND bt.lang = ${param_idx}")
        params.append(lang)
        param_idx += 1
    if sources:
        codes = [c.strip() for c in sources.split(",") if c.strip()]
        if codes:
            placeholders = ", ".join(f"${param_idx + i}" for i in range(len(codes)))
            filter_conditions.append(f"AND ds.code IN ({placeholders})")
            params.extend(codes)
            param_idx += len(codes)

    filter_sql = " ".join(filter_conditions)

    sql = (
        "SELECT te.text_id, te.juan_num, te.chunk_text, "  # nosec B608
        "1 - (te.embedding <=> $1::vector) AS score, "
        "COALESCE(bt.title_zh, '') AS title_zh, "
        "bt.translator, bt.dynasty, bt.category, ds.code AS source_code, "
        "bt.cbeta_id, bt.cbeta_url, "
        "CASE WHEN bt.content_char_count > 0 THEN true ELSE false END AS has_content "
        "FROM text_embeddings te "
        "JOIN buddhist_texts bt ON bt.id = te.text_id "
        "LEFT JOIN data_sources ds ON ds.id = bt.source_id "
        "WHERE te.embedding IS NOT NULL "
        f"AND 1 - (te.embedding <=> $1::vector) >= $2 "
        f"{filter_sql} "
        "ORDER BY te.embedding <=> $1::vector "
        "LIMIT $3"
    )

    try:
        raw_conn = await db.connection()
        result = await raw_conn.exec_driver_sql(sql, tuple(params))
        rows = result.fetchall()
    except Exception:
        logger.exception("语义搜索：数据库查询失败")
        await db.rollback()
        return SemanticSearchResponse(total=0, results=[])

    # 去重：同一 text_id 只保留最高分的 chunk
    seen_texts: dict[int, dict] = {}
    for row in rows:
        text_id = row[0]
        score = float(row[3])
        if text_id not in seen_texts or score > seen_texts[text_id]["score"]:
            seen_texts[text_id] = {
                "text_id": text_id,
                "juan_num": row[1],
                "snippet": row[2][:300] if row[2] else "",  # 截取前300字符作为摘要
                "score": score,
                "title_zh": row[4],
                "translator": row[5],
                "dynasty": row[6],
                "category": row[7],
                "source_code": row[8],
                "cbeta_id": row[9],
                "cbeta_url": row[10],
                "has_content": row[11],
            }

    # 按相似度降序排列
    sorted_results = sorted(seen_texts.values(), key=lambda r: r["score"], reverse=True)[:size]

    hits = [
        SemanticSearchHit(
            text_id=r["text_id"],
            juan_num=r["juan_num"],
            title_zh=r["title_zh"],
            translator=r["translator"],
            dynasty=r["dynasty"],
            category=r["category"],
            source_code=r["source_code"],
            cbeta_id=r["cbeta_id"],
            cbeta_url=r["cbeta_url"],
            has_content=r["has_content"],
            snippet=r["snippet"],
            similarity_score=round(r["score"], 4),
        )
        for r in sorted_results
    ]

    return SemanticSearchResponse(total=len(hits), results=hits)
