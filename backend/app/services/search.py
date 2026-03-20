import logging

from elasticsearch import AsyncElasticsearch

from app.core.elasticsearch import CONTENT_INDEX_NAME, INDEX_NAME
from app.schemas.text import SearchHit, SearchResponse

logger = logging.getLogger(__name__)


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
