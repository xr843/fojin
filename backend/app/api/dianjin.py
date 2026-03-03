import json
import logging

from fastapi import APIRouter, Query, Request

from app.schemas.dianjin import (
    DianjinDatasourcePage,
    DianjinHealthResponse,
    DianjinSearchResponse,
)
from app.services.dianjin import DianjinAPIError, get_dianjin_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dianjin", tags=["dianjin"])

CACHE_TTL = 3600  # 1 hour


async def _get_redis(request: Request):
    try:
        return request.app.state.redis
    except Exception:
        return None


async def _cached_get(request: Request, cache_key: str, fetch_fn):
    redis = await _get_redis(request)
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    result = await fetch_fn()

    if redis:
        try:
            await redis.set(cache_key, json.dumps(result, default=str), ex=CACHE_TTL)
        except Exception:
            pass

    return result


@router.get("/health", response_model=DianjinHealthResponse)
async def dianjin_health():
    """检查典津 API 连通性和认证状态。"""
    try:
        client = get_dianjin_client()
        return await client.health_check()
    except Exception as e:
        logger.exception("Dianjin health check failed")
        return DianjinHealthResponse(error=f"健康检查失败: {str(e)}")


@router.get("/datasources")
async def dianjin_datasources(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """浏览典津数据源列表（公开，缓存 1h）。"""
    cache_key = f"dianjin:datasources:{page}:{size}"

    async def fetch():
        client = get_dianjin_client()
        result = await client.get_datasources(page=page, size=size)
        return result.model_dump()

    try:
        return await _cached_get(request, cache_key, fetch)
    except DianjinAPIError as e:
        return {"error": e.detail, "items": [], "total": 0}
    except Exception as e:
        logger.exception("Dianjin datasources fetch failed")
        return {"error": f"获取数据源失败: {str(e)}", "items": [], "total": 0}


@router.get("/region-labels")
async def dianjin_region_labels(request: Request):
    """获取典津地区代码→中文名映射（公开，缓存 1h）。"""
    cache_key = "dianjin:region-labels"

    async def fetch():
        client = get_dianjin_client()
        return await client.get_region_labels()

    try:
        return await _cached_get(request, cache_key, fetch)
    except Exception as e:
        logger.exception("Dianjin region-labels fetch failed")
        return {}


@router.get("/institutions")
async def dianjin_institutions(request: Request):
    """获取典津机构列表（含地区信息，公开，缓存 1h）。"""
    cache_key = "dianjin:institutions"

    async def fetch():
        client = get_dianjin_client()
        return await client.get_institutions()

    try:
        return await _cached_get(request, cache_key, fetch)
    except Exception as e:
        logger.exception("Dianjin institutions fetch failed")
        return []


@router.post("/search", response_model=DianjinSearchResponse)
async def dianjin_search(
    query: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """代理搜索请求到典津平台（需认证）。"""
    try:
        client = get_dianjin_client()
        return await client.search(query=query, page=page, size=size)
    except Exception as e:
        logger.exception("Dianjin search failed")
        return DianjinSearchResponse(error=f"典津搜索异常: {str(e)}")
