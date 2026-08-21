import logging
from collections import defaultdict

from elasticsearch import AsyncElasticsearch
from sqlalchemy import or_, select
from sqlalchemy import text as sql_text
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
from app.services.gaiji import GaijiNormalizer, expand_for_query
from app.services.rag_retrieval import MIN_RELEVANCE_SCORE

logger = logging.getLogger(__name__)


def _gaiji_should_clauses(query: str, normalizer: GaijiNormalizer | None) -> list[dict]:
    """Build ES should-clauses that match the gaiji alternates for each
    distinct character in the query.

    Returns an empty list when no normalizer is configured or no character
    in the query is a known gaiji glyph — in that case the caller's
    existing single-match query is used unchanged (zero behavior change
    for non-gaiji searches).
    """
    if not normalizer or not query:
        return []
    clauses: list[dict] = []
    seen_alternates: set[str] = set()
    for char in dict.fromkeys(query):  # preserve order, dedupe
        for alt in expand_for_query(char, normalizer):
            if alt in seen_alternates:
                continue
            seen_alternates.add(alt)
            # match_phrase keeps the composition bracket / PUA codepoint
            # intact in indexed content; a regular match would tokenize
            # the brackets away under the cjk_content analyzer.
            clauses.append({"match_phrase": {"content": alt}})
    return clauses


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


# Expand common sutra abbreviations to full titles. Module-level so the
# cross-module consistency test can read it: this table and
# precise_retrieval._TITLE_ALIASES must not send the same abbreviation to
# two different sutras (they did, for 楞伽经).
_SUTRA_ABBREV: dict[str, str] = {
    "金刚经": "金剛般若波羅蜜經", "金剛經": "金剛般若波羅蜜經",
    "心经": "般若波羅蜜多心經", "心經": "般若波羅蜜多心經",
    "法华经": "妙法蓮華經", "法華經": "妙法蓮華經",
    "华严经": "大方廣佛華嚴經", "華嚴經": "大方廣佛華嚴經",
    "楞严经": "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經", "楞嚴經": "大佛頂如來密因修證了義諸菩薩萬行首楞嚴經",
    "圆觉经": "大方廣圓覺修多羅了義經", "圓覺經": "大方廣圓覺修多羅了義經",
    # 楞伽經 has three Chinese translations — T0670 楞伽阿跋多羅寶經
    # (求那跋陀羅, 4卷), T0671 入楞伽經 (菩提流支, 10卷), T0672 大乘入楞伽經
    # (實叉難陀, 7卷). This table used to boost T0671 while
    # precise_retrieval._TITLE_ALIASES and rag_retrieval._ROOT_SUTRA_ALIASES
    # both resolve the same abbreviation to T0670, so the one word 楞伽经
    # reached a different sutra depending on which door the reader came in.
    # Aligned on T0670 — the recension Chan transmits and the one usually
    # meant unqualified. All three still rank; this is a boost, not a filter.
    "楞伽经": "楞伽阿跋多羅寶經", "楞伽經": "楞伽阿跋多羅寶經",
    "维摩经": "維摩詰所說經", "維摩經": "維摩詰所說經",
    "地藏经": "地藏菩薩本願經", "地藏經": "地藏菩薩本願經",
    "药师经": "藥師琉璃光如來本願功德經", "藥師經": "藥師琉璃光如來本願功德經",
    "阿弥陀经": "佛說阿彌陀經", "阿彌陀經": "佛說阿彌陀經",
    "无量寿经": "佛說無量壽經", "無量壽經": "佛說無量壽經",
    "涅盘经": "大般涅槃經", "涅槃經": "大般涅槃經",
    "般若经": "大般若波羅蜜多經", "般若經": "大般若波羅蜜多經",
    "长阿含经": "長阿含經", "长阿含經": "長阿含經",
    "中阿含经": "中阿含經", "杂阿含经": "雜阿含經",
    "增一阿含经": "增壹阿含經",
    "坛经": "六祖大師法寶壇經", "壇經": "六祖大師法寶壇經",
}


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

    full_title = _SUTRA_ABBREV.get(query.strip())

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
        # Boost the full title if query is a known abbreviation (in should, not must)
        should_boosts = [
            {"match_phrase": {"title_zh": {"query": query, "boost": 15}}},
            {"match_phrase": {"title_en": {"query": query, "boost": 8}}},
        ]
        if full_title:
            should_boosts.append(
                {"match_phrase": {"title_zh": {"query": full_title, "boost": 30}}}
            )
        must.append({"bool": {"should": should_boosts, "minimum_should_match": 0}})
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
        # title_zh is analyzed text; its keyword sub-field is mapped as "raw",
        # not "keyword" (see INDEX_SETTINGS in app/core/elasticsearch.py).
        sort_clause = [{"title_zh.raw": "asc"}, "_score"]
    elif sort == "dynasty":
        # dynasty is mapped directly as `keyword` (no analyzed variant), so it
        # has no ".keyword" sub-field — sort on the field itself.
        sort_clause = [{"dynasty": "asc"}, "_score"]
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

    # Deduplicate: same title+translator → keep best version (smallest taisho_id)
    # Different translators of the same sutra are preserved as separate results
    import re as _re
    _DYNASTY_PREFIX = _re.compile(r"^(魏|隋|唐|宋|元|明|清|南朝|北朝|十六國|東晉|西晉|後秦|後漢|姚秦|劉宋|蕭齊|梁|陳|北魏|北齊|北周|東魏|西魏|南齊|蜀|吳)\s*")
    def _norm_translator(t):
        if not t:
            return ""
        return _DYNASTY_PREFIX.sub("", t).strip()

    seen_keys: dict[str, int] = {}
    deduped: list = []
    for r in results:
        key = (r.title_zh or "") + "|" + _norm_translator(r.translator)
        if key in seen_keys:
            existing = deduped[seen_keys[key]]
            existing_tid = existing.taisho_id or "ZZZZ"
            new_tid = r.taisho_id or "ZZZZ"
            if (r.has_content and not existing.has_content) or new_tid < existing_tid:
                deduped[seen_keys[key]] = r
        else:
            seen_keys[key] = len(deduped)
            deduped.append(r)
    results = deduped

    return SearchResponse(total=total, page=page, size=size, results=results, suggestion=suggestion)


async def search_content(
    es: AsyncElasticsearch,
    query: str,
    page: int = 1,
    size: int = 20,
    sources: str | None = None,
    lang: str | None = None,
    gaiji_normalizer: GaijiNormalizer | None = None,
) -> dict:
    """Search full-text content in Elasticsearch.

    When ``gaiji_normalizer`` is provided, the query is expanded with
    OR-clauses matching the CBETA gaiji alternate spellings of each
    character (composition expressions and PUA codepoints), so that
    searches like "款" also match passages encoded as "[肄-聿+欠]".
    Passing ``None`` preserves the pre-1.3c2 behavior exactly.
    """
    if not query:
        return {"total": 0, "page": page, "size": size, "results": []}

    primary_clause: dict = {
        "match": {
            "content": {
                "query": query,
                "analyzer": "cjk_content",
            }
        }
    }

    gaiji_clauses = _gaiji_should_clauses(query, gaiji_normalizer)
    if gaiji_clauses:
        content_query: dict = {
            "bool": {
                "should": [primary_clause, *gaiji_clauses],
                "minimum_should_match": 1,
            }
        }
        logger.info(
            "gaiji query expansion: query=%r added %d alternate clauses",
            query,
            len(gaiji_clauses),
        )
    else:
        content_query = primary_clause

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


# ---------------------------------------------------------------------------
# Cross-lingual parallel sentences (MITRA)
# ---------------------------------------------------------------------------
#
# Query a Chinese phrase, get aligned Sanskrit/Tibetan sentences (with their
# Chinese counterpart + source) mined by the MITRA project over pilot Taishō
# texts. Reads mitra_alignments (~896K sentence-level rows, Skt/Tib↔汉),
# populated on prod; coverage is deliberately sparse (10 pilot texts today,
# more after a future full import), so an empty result is the natural dark
# state — no feature flag.
#
# Match strategy — ILIKE substring on zh_text (precise phrase containment,
# the useful primitive for "find the aligned foreign sentence for this 汉
# phrase") with pg_trgm ``similarity`` as the match-quality ranking signal
# (a sentence that *is* the query ranks above a long one merely containing
# it). pg_trgm is available (see CLAUDE.md / DECISIONS.md).
#
# Index behavior — migration 0156/0169 index mitra_alignments only on
# (text_id, juan_num, chunk_index[, mitra_e_score]), taisho_id, and text_id;
# there is NO btree/trgm index on zh_text (nor on foreign_lang). So the phrase
# match is a filtered sequential scan. We bound worst-case cost with an early
# ``LIMIT :scan_cap`` candidate cut *before* the similarity sort, so a
# hyper-common substring can't force an unbounded sort over the whole table
# (Postgres stops scanning once scan_cap matches are collected). A future
# ``gin_trgm_ops`` index on zh_text (owned by a migration, out of scope here)
# would make this index-accelerated and let the ranking see the global best
# candidates — see TODO below.
#
# Ranking — (1) match quality (pg_trgm similarity of zh_text vs the query),
# (2) mitra_e_score DESC NULLS LAST, (3) id. The mitra_e_score ordering is
# NULL-PERMISSIVE (unscored rows are still returned, ranked last within a
# score tier), mirroring the established _attach_mitra_parallels gate: there
# is no ``mitra_e_score >= x`` predicate, so this stays a no-op until a prod
# backfill populates the column.

# Cap on the candidate rows pulled before the similarity sort — bounds the
# per-query scan/sort when a common phrase matches a huge number of rows.
PARALLEL_SCAN_CAP = 500


def _dedup_parallel_key(foreign_lang: str, foreign_text: str) -> tuple[str, str]:
    """Key for collapsing near-identical foreign sentences.

    Normalizes away case + whitespace differences (common across MITRA's
    Sanskrit/Tibetan romanizations) and keys on a leading window, so two
    rows that differ only by spacing/casing collapse to one.
    """
    normalized = "".join((foreign_text or "").lower().split())[:80]
    return (foreign_lang or "", normalized)


async def search_parallel_sentences(
    db: AsyncSession,
    query: str,
    lang: str = "all",
    limit: int = 20,
) -> list[dict]:
    """Aligned foreign-language sentences whose Chinese counterpart matches ``query``.

    Set-based single query (no N+1): filter mitra_alignments.zh_text by ILIKE
    substring (+ optional foreign_lang), rank by pg_trgm match quality then
    mitra_e_score DESC NULLS LAST then id, join buddhist_texts for the title.
    Near-identical foreign sentences are deduped in Python (preserving the SQL
    rank order — the highest-ranked copy wins). Returns up to ``limit`` plain
    dicts; the router wraps them in the response schema.

    TODO(sentence_alignments): once the verified 汉巴/汉藏 store
    (sentence_alignments) is populated, UNION it in here (tagged source so the
    card can badge "verified" vs MITRA), ordering verified rows ahead of MITRA.
    """
    q = (query or "").strip()
    if not q:
        return []

    # Escape LIKE metacharacters in the user phrase so they match literally.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    params: dict = {
        "q": q,
        "pattern": f"%{escaped}%",
        "scan_cap": PARALLEL_SCAN_CAP,
        "limit": max(1, limit),
    }

    lang_clause = ""
    if lang in ("sa", "bo"):
        lang_clause = "AND foreign_lang = :lang"
        params["lang"] = lang

    # candidates: bounded scan (LIMIT before the sort caps work on common
    # phrases). ranked: apply match-quality + NULL-permissive score ordering
    # over the (small) candidate set, then join the title.
    sql = sql_text(f"""
        WITH candidates AS (
            SELECT id, zh_text, foreign_text, foreign_lang, taisho_id,
                   text_id, juan_num, mitra_e_score, source, license
            FROM mitra_alignments
            WHERE zh_text ILIKE :pattern ESCAPE '\\'
              {lang_clause}
            LIMIT :scan_cap
        )
        SELECT c.zh_text, c.foreign_text, c.foreign_lang, c.taisho_id,
               c.text_id, c.juan_num, c.mitra_e_score, c.source, c.license,
               COALESCE(bt.title_zh, '') AS title
        FROM candidates c
        LEFT JOIN buddhist_texts bt ON bt.id = c.text_id
        ORDER BY similarity(c.zh_text, :q) DESC,
                 c.mitra_e_score DESC NULLS LAST,
                 c.id
        LIMIT :scan_cap
    """)

    try:
        rows = (await db.execute(sql, params)).fetchall()
    except Exception:
        logger.exception("跨语对照搜索：数据库查询失败")
        await db.rollback()
        return []

    seen: set[tuple[str, str]] = set()
    results: list[dict] = []
    for row in rows:
        (zh_text, foreign_text, foreign_lang, taisho_id, text_id,
         juan_num, mitra_e_score, source, license_, title) = row
        if not foreign_text:
            continue
        key = _dedup_parallel_key(foreign_lang, foreign_text)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "zh_text": zh_text or "",
            "foreign_text": foreign_text,
            "foreign_lang": foreign_lang or "sa",
            "taisho_id": taisho_id or "",
            "text_id": text_id,
            "title": title or "",
            "juan_num": juan_num,
            "mitra_e_score": float(mitra_e_score) if mitra_e_score is not None else None,
            "source": source or "mitra-parallel",
            "license": license_ or "CC-BY-SA-4.0",
        })
        if len(results) >= max(1, limit):
            break

    return results
