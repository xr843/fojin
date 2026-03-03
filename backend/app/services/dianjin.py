import logging

import httpx

from app.config import settings
from app.schemas.dianjin import (
    DianjinDatasource,
    DianjinDatasourcePage,
    DianjinHealthResponse,
    DianjinSearchHit,
    DianjinSearchResponse,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://guji.cckb.cn"


class DianjinAPIError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Dianjin API error {status_code}: {detail}")


class DianjinClient:
    """HTTP client for the Dianjin (典津) platform API at guji.cckb.cn."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0),
                headers={"User-Agent": "FoJin/3.0"},
            )
        return self._client

    @property
    def _api_key(self) -> str:
        return settings.dianjin_api_key

    @property
    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    # ─── Public endpoint ───

    async def get_datasources(self, page: int = 1, size: int = 20) -> DianjinDatasourcePage:
        """GET /api/public/datasources — 公开，无需认证。"""
        client = await self._get_client()
        resp = await client.get(
            "/api/public/datasources",
            params={"page": page, "size": size},
        )
        resp.raise_for_status()
        data = resp.json()
        items = [
            DianjinDatasource(
                id=item.get("id", ""),
                name=item.get("name", ""),
                code=item.get("code", ""),
                description=item.get("description", ""),
                category=item.get("category", ""),
                tags=item.get("tags", []),
                institution_code=item.get("institutionCode", ""),
                record_count=item.get("recordCount", 0),
            )
            for item in data.get("items", [])
        ]
        return DianjinDatasourcePage(
            items=items,
            total=data.get("total", 0),
            page=data.get("page", page),
            size=data.get("size", size),
            total_pages=data.get("totalPages", 0),
        )

    async def get_region_labels(self) -> dict[str, str]:
        """GET /api/public/datasources/region-labels — 地区代码→中文名映射。"""
        client = await self._get_client()
        resp = await client.get("/api/public/datasources/region-labels")
        resp.raise_for_status()
        return resp.json().get("items", {})

    async def get_institutions(self) -> list[dict]:
        """GET /api/public/datasources/institutions — 机构列表（含 countryRegion）。"""
        client = await self._get_client()
        resp = await client.get("/api/public/datasources/institutions")
        resp.raise_for_status()
        return resp.json().get("items", [])

    # ─── Authenticated endpoint ───

    async def search(self, query: str, page: int = 1, size: int = 20) -> DianjinSearchResponse:
        """POST /api/search — 需要 Bearer token。"""
        if not self._api_key:
            return DianjinSearchResponse(error="典津 API Key 未配置")
        client = await self._get_client()
        try:
            resp = await client.post(
                "/api/search",
                headers=self._auth_headers,
                json={"query": query, "page": page, "size": size},
            )
            if resp.status_code == 401:
                return DianjinSearchResponse(error="典津 API token 无效或已过期")
            if resp.status_code >= 500:
                return DianjinSearchResponse(error="典津搜索服务暂时不可用")
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("items", []):
                # standardFields 是 [{name, displayName, value}, ...] 格式
                fields = {f["name"]: f["value"] for f in item.get("standardFields", [])}
                scores = item.get("scores", {})
                detail_path = fields.get("detailUrl")
                results.append(DianjinSearchHit(
                    id=item.get("id", ""),
                    title=fields.get("title", ""),
                    datasource_name=item.get("datasourceName"),
                    datasource_category=item.get("datasourceCategory"),
                    datasource_tags=item.get("datasourceTags", []),
                    collection=fields.get("collection"),
                    main_responsibility=fields.get("mainResponsibility"),
                    edition=fields.get("edition"),
                    detail_url=f"{BASE_URL}{detail_path}" if detail_path else None,
                    score=scores.get("finalScore"),
                ))
            return DianjinSearchResponse(
                total=data.get("total", len(results)),
                page=page,
                size=size,
                results=results,
                search_time=data.get("searchTime"),
            )
        except httpx.TimeoutException:
            return DianjinSearchResponse(error="典津搜索请求超时")
        except httpx.HTTPStatusError as e:
            return DianjinSearchResponse(error=f"典津 API 错误: {e.response.status_code}")
        except Exception as e:
            logger.exception("Dianjin search unexpected error")
            return DianjinSearchResponse(error=f"典津搜索异常: {str(e)}")

    # ─── Health check ───

    async def health_check(self) -> DianjinHealthResponse:
        result = DianjinHealthResponse(configured=bool(self._api_key))
        client = await self._get_client()

        # Test public API via datasources endpoint
        try:
            resp = await client.get("/api/public/datasources", params={"page": 1, "size": 1})
            result.public_api = resp.status_code == 200
            if resp.status_code == 200:
                data = resp.json()
                result.datasource_count = data.get("total", 0)
        except Exception as e:
            result.error = f"公开 API 不可达: {str(e)}"

        # Test search API (only if configured)
        if self._api_key:
            try:
                resp = await client.post(
                    "/api/search",
                    headers=self._auth_headers,
                    json={"query": "test", "page": 1, "size": 1},
                )
                if resp.status_code == 200:
                    result.search_api = True
                elif resp.status_code == 401:
                    result.error = "典津 API token 无效或已过期"
                elif resp.status_code >= 500:
                    result.error = "典津搜索服务暂时不可用"
            except Exception as e:
                if not result.error:
                    result.error = f"搜索 API 不可达: {str(e)}"

        return result

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Module-level singleton
_client: DianjinClient | None = None


def get_dianjin_client() -> DianjinClient:
    global _client
    if _client is None:
        _client = DianjinClient()
    return _client
