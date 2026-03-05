from elasticsearch import AsyncElasticsearch

from app.core.elasticsearch import CONTENT_INDEX_NAME, INDEX_NAME
from app.schemas.text import SearchHit, SearchResponse


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

    return SearchResponse(total=total, page=page, size=size, results=results)


async def search_content(
    es: AsyncElasticsearch,
    query: str,
    page: int = 1,
    size: int = 20,
    sources: str | None = None,
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

    # Wrap in bool query if sources filter is present
    if sources:
        codes = [c.strip() for c in sources.split(",") if c.strip()]
        if codes:
            source_filter = {"term": {"source_code": codes[0]}} if len(codes) == 1 else {"terms": {"source_code": codes}}
            content_query = {
                "bool": {
                    "must": [content_query],
                    "filter": [source_filter],
                }
            }

    body = {
        "query": content_query,
        "highlight": {
            "fields": {
                "content": {
                    "fragment_size": 120,
                    "number_of_fragments": 3,
                    "pre_tags": ["<em>"],
                    "post_tags": ["</em>"],
                }
            }
        },
        "from": (page - 1) * size,
        "size": size,
    }

    result = await es.search(index=CONTENT_INDEX_NAME, body=body, timeout="10s")
    hits = result["hits"]
    total = hits["total"]["value"]

    results = []
    for hit in hits["hits"]:
        src = hit["_source"]
        results.append({
            "text_id": src["text_id"],
            "cbeta_id": src.get("cbeta_id", ""),
            "title_zh": src.get("title_zh", ""),
            "translator": src.get("translator"),
            "dynasty": src.get("dynasty"),
            "juan_num": src.get("juan_num", 1),
            "highlight": hit.get("highlight", {}).get("content", []),
            "score": hit["_score"],
        })

    return {"total": total, "page": page, "size": size, "results": results}


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
