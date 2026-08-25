import asyncio
import time

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import get_es
from app.database import get_db
from app.models.dictionary import DictionaryEntry
from app.models.hot_question import HotQuestion
from app.schemas.text import CrossLanguageSearchResponse, SearchResponse, SemanticSearchResponse
from app.services.search import (
    _SUTRA_ABBREV,
    get_aggregations,
    get_suggestions,
    search_content,
    search_cross_language,
    search_parallel_sentences,
    search_semantic,
    search_texts,
)

try:
    from app.schemas.dianjin import FederatedSearchResponse
    from app.services.dianjin import get_dianjin_client
    _HAS_DIANJIN = True
except ImportError:
    _HAS_DIANJIN = False

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    dynasty: str | None = Query(None, description="朝代筛选"),
    category: str | None = Query(None, description="分类筛选"),
    lang: str | None = Query(None, description="语言筛选 (lzh/pi/sa/bo/en)"),
    sources: str | None = Query(None, description="数据源筛选，逗号分隔 (cbeta,suttacentral,gretil)"),
    sort: str | None = Query(None, description="排序方式 (relevance/title/dynasty)"),
    db: AsyncSession = Depends(get_db),
):
    """Search Buddhist texts by title, ID, translator, etc. with faceted filtering.

    搜索佛教典籍。支持经名、编号、译者等多字段搜索，可按朝代、分类、语言和数据源筛选。"""
    es = get_es()
    return await search_texts(es, q, page, size, dynasty, category, lang, sources, sort, db=db)


def _alias_titles(q: str) -> list[str]:
    """别名前缀命中的正典经名：「金刚」「金刚经」→ 金剛般若波羅蜜經。去重保序，至多 3。

    表是 services/search.py 的 _SUTRA_ABBREV —— 与问答检索、搜索共用一张，别再抄一份。
    """
    q = q.strip()
    if not q:
        return []
    out: list[str] = []
    for alias, title in _SUTRA_ABBREV.items():
        if alias.startswith(q) and title not in out:
            out.append(title)
        if len(out) >= 3:
            break
    return out


async def _dict_suggestions(db: AsyncSession, q: str) -> tuple[list[str], list[str]]:
    """辞典词头：(精确命中, 前缀命中≤5)。300k+ 词头，只查前缀。"""
    try:
        stmt = (
            select(DictionaryEntry.headword)
            .where(DictionaryEntry.headword.ilike(f"{q}%"))
            .group_by(DictionaryEntry.headword)
            .order_by(func.length(DictionaryEntry.headword), DictionaryEntry.headword)
            .limit(6)
        )
        rows = await db.execute(stmt)
        heads = [r[0] for r in rows.all() if r[0]]
    except Exception:
        return [], []
    exact = [h for h in heads if h == q]
    prefix = [h for h in heads if h != q][:5]
    return exact, prefix


async def _hot_question_suggestions(db: AsyncSession, q: str) -> list[str]:
    """精选问题（200 条人工策展）里含关键词的，至多 3 条。"""
    try:
        stmt = (
            select(HotQuestion.display_text)
            .where(HotQuestion.is_active.is_(True))
            .where(HotQuestion.display_text.ilike(f"%{q}%"))
            .order_by(HotQuestion.sort_order.asc())
            .limit(3)
        )
        rows = await db.execute(stmt)
        return [r[0] for r in rows.all() if r[0]]
    except Exception:
        return []


@router.get("/search/suggest")
async def search_suggest(
    q: str = Query(..., min_length=1, max_length=200, description="搜索建议关键词"),
    db: AsyncSession = Depends(get_db),
):
    """Return autocomplete suggestions across multiple sources.

    Ranking (2026-08-25 — before this, dictionary headwords sorted by length
    always came first, so "金刚" produced 金刚/金刚石/金刚砂/金刚宝石 and the
    site's most-searched sutra 《金刚经》 was not in the list at all):

    1. canonical titles whose alias starts with the query (services/search.py
       ``_SUTRA_ABBREV`` — shared with retrieval and search)
    2. exact dictionary headword ("苦" still surfaces the entry 苦 first)
    3. ES title prefix matches (sutra titles & translators)
    4. dictionary prefix headwords (金刚石 …)
    5. hot_questions containing the query

    Each item carries a ``type`` (title / term / question) so the homepage can
    group the dropdown; ``suggestions`` stays a flat string list for the search
    page. Deduplicated, at most 10.

    根据输入返回搜索建议（自动补全）：正典经名 > 精确词头 > 经名 > 前缀词头 > 精选问题。"""
    es = get_es()

    es_titles, (dict_exact, dict_prefix), hot = await asyncio.gather(
        get_suggestions(es, q),
        _dict_suggestions(db, q),
        _hot_question_suggestions(db, q),
    )

    seen: set[str] = set()
    items: list[dict[str, str]] = []

    def _add(values: list[str], kind: str) -> None:
        for v in values:
            if v and v not in seen and len(items) < 10:
                seen.add(v)
                items.append({"value": v, "type": kind})

    _add(_alias_titles(q), "title")
    _add(dict_exact, "term")
    _add(es_titles, "title")
    _add(dict_prefix, "term")
    _add(hot, "question")

    return {"suggestions": [i["value"] for i in items], "items": items}


@router.get("/search/cross-language", response_model=CrossLanguageSearchResponse)
async def cross_language_search(
    q: str = Query("", max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    dynasty: str | None = Query(None, description="朝代筛选"),
    category: str | None = Query(None, description="分类筛选"),
    sources: str | None = Query(None, description="数据源筛选，逗号分隔"),
    db: AsyncSession = Depends(get_db),
):
    """Cross-language search across all title fields (zh, en, sa, pi, bo).

    跨语言搜索：同时搜索所有语种标题字段，自动获取相关翻译版本，按"作品族"分组展示。"""
    es = get_es()
    return await search_cross_language(es, q, page, size, dynasty, category, sources, db=db)


@router.get("/search/content")
async def content_search(
    request: Request,
    q: str = Query("", max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    sources: str | None = Query(None, description="数据源筛选，逗号分隔"),
    lang: str | None = Query(None, description="语言筛选 (lzh/pi/en)"),
):
    """Full-text content search across scripture bodies with keyword highlighting.

    全文内容搜索。搜索经文正文并高亮显示匹配段落。Rate limit: 30/min."""
    es = get_es()
    gaiji_normalizer = getattr(request.app.state, "gaiji_normalizer", None)
    return await search_content(
        es, q, page, size, sources, lang, gaiji_normalizer=gaiji_normalizer
    )


@router.get("/search/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    q: str = Query("", max_length=200, description="语义搜索关键词"),
    size: int = Query(20, ge=1, le=50, description="返回数量"),
    dynasty: str | None = Query(None, description="朝代筛选"),
    category: str | None = Query(None, description="分类筛选"),
    lang: str | None = Query(None, description="语言筛选 (lzh/pi/sa/bo/en)"),
    sources: str | None = Query(None, description="数据源筛选，逗号分隔 (cbeta,suttacentral,gretil)"),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search using pgvector embedding similarity.

    语义搜索。基于向量相似度在 34.7 万段经文中检索语义最相关的内容。支持按朝代、分类、语言和数据源筛选。"""
    # Strip first so blank/whitespace-only queries short-circuit before the
    # paid embedding call and can't each bust the embedding cache.
    return await search_semantic(db, q.strip(), size, dynasty, category, lang, sources)


# --- Cross-lingual parallel sentences (MITRA) ------------------------------
# Response schema defined inline here (mirrors api/alignment.py's inline
# ParallelPair/*Response contracts) rather than in schemas/text.py.


class ParallelSentenceHit(BaseModel):
    """One aligned sentence pair from mitra_alignments (MITRA, CC BY-SA 4.0).

    ``foreign_text`` is the inline Sanskrit/Tibetan sentence; ``zh_text`` is its
    Chinese counterpart. ``mitra_e_score`` is a nullable quality proxy (NULL
    until a prod backfill runs — unscored rows are still returned).
    """
    zh_text: str
    foreign_text: str
    foreign_lang: str
    taisho_id: str
    text_id: int
    title: str = ""
    juan_num: int | None = None
    mitra_e_score: float | None = None
    source: str = "mitra-parallel"
    license: str = "CC-BY-SA-4.0"


class ParallelSentencesResponse(BaseModel):
    total: int
    results: list[ParallelSentenceHit]
    error: str | None = None


@router.get("/search/parallel-sentences", response_model=ParallelSentencesResponse)
async def parallel_sentences_search(
    q: str = Query("", max_length=200, description="中文关键词（跨语对照）"),
    lang: str = Query("all", description="外语筛选 (sa 梵 / bo 藏 / all 全部)"),
    limit: int = Query(20, ge=1, le=50, description="返回数量"),
    db: AsyncSession = Depends(get_db),
) -> ParallelSentencesResponse:
    """Cross-lingual sentence search over MITRA parallels.

    输入中文短语，返回对齐的梵/藏语句及其汉文对照与出处（MITRA 平行语料，
    CC BY-SA 4.0）。以 pg_trgm 相似度对 zh_text 排序，mitra_e_score 降序
    （NULL 宽容），支持按外语语种筛选。数据覆盖随导入逐步增长，空结果为常态。"""
    # Strip first so blank/whitespace-only queries short-circuit before any
    # DB scan (search_parallel_sentences also guards, but keep the router thin
    # and consistent with /search/semantic).
    rows = await search_parallel_sentences(db, q.strip(), lang, limit)
    return ParallelSentencesResponse(
        total=len(rows),
        results=[ParallelSentenceHit(**r) for r in rows],
    )


_filters_cache: dict = {"data": None, "expires": 0}

@router.get("/filters")
async def filters(db: AsyncSession = Depends(get_db)):
    """Get available filter facets (dynasty, category, language, source). Cached for 5 minutes.

    获取可用的筛选选项（朝代、分类、语言、数据源）。缓存 5 分钟。"""
    if _filters_cache["data"] and time.time() < _filters_cache["expires"]:
        return _filters_cache["data"]
    es = get_es()
    aggs = await get_aggregations(es)

    # languages_with_data: languages that have actual text records in DB (from ES agg)
    languages_with_data = sorted(aggs.get("languages", []))

    # languages_all: all languages covered by active data sources
    from sqlalchemy import text as sa_text
    result = await db.execute(
        sa_text("SELECT languages FROM data_sources WHERE is_active = true AND languages IS NOT NULL AND languages != ''")
    )
    all_langs = set()
    for row in result.fetchall():
        for lang in row[0].split(","):
            lang = lang.strip()
            if lang:
                all_langs.add(lang)

    aggs["languages"] = languages_with_data
    aggs["languages_all"] = sorted(all_langs)
    _filters_cache["data"] = aggs
    _filters_cache["expires"] = time.time() + 300  # 5 min TTL
    return aggs


if _HAS_DIANJIN:

    @router.get("/search/federated", response_model=FederatedSearchResponse)
    async def federated_search(
        q: str = Query("", max_length=200, description="搜索关键词"),
        page: int = Query(1, ge=1, description="页码"),
        size: int = Query(20, ge=1, le=100, description="每页数量"),
        dynasty: str | None = Query(None, description="朝代筛选"),
        category: str | None = Query(None, description="分类筛选"),
        lang: str | None = Query(None, description="语言筛选"),
        sources: str | None = Query(None, description="数据源筛选"),
        include_dianjin: bool = Query(True, description="是否包含典津结果"),
    ):
        """Federated search across local database and Dianjin cross-platform ancient text resources.

        联合检索：同时搜索本地数据库和典津跨平台古籍资源。"""
        es = get_es()

        # Build coroutines
        local_coro = search_texts(es, q, page, size, dynasty, category, lang, sources)

        dianjin_result = None
        if include_dianjin and q:
            dianjin_client = get_dianjin_client()
            dianjin_coro = dianjin_client.search(query=q, page=page, size=size)
            local_result, dianjin_result = await asyncio.gather(
                local_coro, dianjin_coro, return_exceptions=True
            )
        else:
            local_result = await local_coro

        # Handle local result
        if isinstance(local_result, Exception):
            local_data = SearchResponse(total=0, page=page, size=size, results=[])
        else:
            local_data = local_result

        # Handle dianjin result
        dianjin_total = 0
        dianjin_results = []
        dianjin_error = None

        if dianjin_result is not None:
            if isinstance(dianjin_result, Exception):
                dianjin_error = f"典津搜索异常: {dianjin_result!s}"
            else:
                dianjin_total = dianjin_result.total
                dianjin_results = dianjin_result.results
                dianjin_error = dianjin_result.error
        elif not include_dianjin or not q:
            dianjin_error = None

        return FederatedSearchResponse(
            local_total=local_data.total,
            local_results=[r.model_dump() for r in local_data.results],
            dianjin_total=dianjin_total,
            dianjin_results=dianjin_results,
            dianjin_error=dianjin_error,
            combined_total=local_data.total + dianjin_total,
        )
