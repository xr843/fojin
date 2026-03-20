import asyncio
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import get_es
from app.database import get_db
from app.schemas.text import SearchResponse
from app.services.search import get_aggregations, get_suggestions, search_content, search_texts

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
):
    """搜索佛教典籍。支持经名、编号、译者等多字段搜索，可按语言和数据源筛选。"""
    es = get_es()
    return await search_texts(es, q, page, size, dynasty, category, lang, sources, sort)


@router.get("/search/suggest")
async def search_suggest(
    q: str = Query(..., min_length=1, max_length=200, description="搜索建议关键词"),
):
    """根据输入返回搜索建议（自动补全）。"""
    es = get_es()
    suggestions = await get_suggestions(es, q)
    return {"suggestions": suggestions}


@router.get("/search/content")
async def content_search(
    q: str = Query("", max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    sources: str | None = Query(None, description="数据源筛选，逗号分隔"),
    lang: str | None = Query(None, description="语言筛选 (lzh/pi/en)"),
):
    """全文内容搜索。搜索经文正文并高亮显示。"""
    es = get_es()
    return await search_content(es, q, page, size, sources, lang)


_filters_cache: dict = {"data": None, "expires": 0}

@router.get("/filters")
async def filters(db: AsyncSession = Depends(get_db)):
    """获取可用的筛选选项（朝代、分类、语言、数据源）。缓存 5 分钟。"""
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
        """联合检索：同时搜索本地数据库和典津跨平台古籍资源。"""
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
