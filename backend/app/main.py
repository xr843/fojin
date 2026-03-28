import logging
import os
import time
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.elasticsearch import close_es, get_es, init_es
from app.core.exceptions import FoJinError, fojin_error_to_http
from app.core.rate_limit import RateLimitMiddleware
from app.database import engine as async_engine

try:
    from app.services.dianjin import get_dianjin_client
    _HAS_DIANJIN = True
except ImportError:
    _HAS_DIANJIN = False

logger = logging.getLogger(__name__)
from datetime import UTC

from app.api import (
    admin,
    annotations,
    auth,
    bookmarks,
    chat,
    citations,
    dictionary,
    exports,
    feedback,
    history,
    iiif,
    knowledge_graph,
    notification,
    relations,
    rss,
    search,
    sitemap,
    source_suggestions,
    sources,
    stats,
    texts,
)

try:
    from app.api import dianjin
except ImportError:
    dianjin = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await init_es()
    yield
    # Shutdown
    if _HAS_DIANJIN:
        await get_dianjin_client().close()
    await app.state.redis.close()
    await close_es()


_API_DESCRIPTION = """\
**FoJin (佛津)** is a Buddhist digital text platform aggregating scriptures,
translations, dictionaries, and scholarly resources from across the world.

## Overview / 概览

| Metric | Value |
|--------|-------|
| Texts / 经文 | 9,200+ across Mahayana, Theravada, Vajrayana traditions |
| Data sources / 数据源 | 500+ curated sources |
| Languages / 语言 | 30+ including Classical Chinese (lzh), Pali, Sanskrit, Tibetan, English |
| Dictionaries / 辞典 | 6 dictionaries, 285,000+ entries |
| AI Q&A / AI 问答 | RAG-powered Buddhist studies assistant |
| Knowledge Graph / 知识图谱 | Entities, relations, and graph traversal |

## Core Features / 核心功能

- **Full-text search** with faceted filtering by dynasty, language, category, and source
- **Content search** across scripture bodies with keyword highlighting
- **Parallel reading** for comparing translations side by side
- **AI chat** with Retrieval-Augmented Generation grounded in canonical texts
- **Knowledge graph** exploring relationships between people, texts, schools, and concepts
- **IIIF manifests** for interoperable image delivery
- **Citation export** in BibTeX, RIS, and Chicago formats
- **RSS & Sitemap** for syndication and SEO

## Data Attribution / 数据致谢

FoJin aggregates data from the following scholarly sources.
All data is used in compliance with its respective license.

| Source | License | Note |
|--------|---------|------|
| **[CBETA 中华电子佛典协会](https://www.cbeta.org/)** | CC BY-NC-SA 4.0 | 经文数据由 CBETA 中华电子佛典协会提供 / Buddhist text data provided by CBETA |
| **[SuttaCentral](https://suttacentral.net/)** | CC0 1.0 | Early Buddhist texts and translations |
| **[84000](https://read.84000.co/)** | CC BY-NC-ND 3.0 | Translating the Words of the Buddha |
| **[GRETIL](http://gretil.sub.uni-goettingen.de/)** | Academic use | Goettingen Register of Electronic Texts in Indian Languages |
| **[DILA 法鼓佛教学院](https://www.dila.edu.tw/)** | Various | Buddhist authority databases and dictionaries |
| Other sources | Various | See `/api/sources` for full list with individual licenses |

## Rate Limits / 请求频率限制

| Scope | Limit |
|-------|-------|
| Global / 全局 | 200 requests / minute |
| Search / 搜索 | 60 requests / minute |
| Content search / 全文搜索 | 30 requests / minute |

Exceeding these limits returns HTTP 429. Include an `Authorization` header for higher quotas.

## Authentication / 认证

Most read endpoints are public. Write operations (bookmarks, annotations, chat history)
require a JWT Bearer token obtained via `/api/auth/login`.
"""

_OPENAPI_TAGS = [
    {
        "name": "search",
        "description": "Text search, content search, suggestions, and filters / 经文搜索、全文搜索、搜索建议与筛选项",
    },
    {
        "name": "texts",
        "description": "Buddhist text metadata and juan (scroll) content retrieval / 经文元数据与卷内容读取",
    },
    {
        "name": "dictionary",
        "description": "Buddhist dictionary lookup across 6 dictionaries with 285,000+ entries / 佛学辞典检索（六部辞典，28.5万+词条）",
    },
    {
        "name": "knowledge-graph",
        "description": "Knowledge graph: entities, relations, and graph traversal / 知识图谱：实体、关系与图遍历",
    },
    {
        "name": "chat",
        "description": "AI Q&A powered by RAG over canonical Buddhist texts / AI 问答（基于经文的检索增强生成）",
    },
    {
        "name": "relations",
        "description": "Text relations and parallel reading / 经文关系与平行对读",
    },
    {
        "name": "sources",
        "description": "Data source metadata, statistics, and distribution channels / 数据源信息、统计与发行渠道",
    },
    {
        "name": "citations",
        "description": "Academic citation generation (BibTeX, RIS, Chicago) / 学术引用导出",
    },
    {
        "name": "auth",
        "description": "User authentication and account management / 用户认证与账户管理",
    },
    {
        "name": "bookmarks",
        "description": "Personal bookmarks and collections / 个人书签与收藏",
    },
    {
        "name": "history",
        "description": "Reading history tracking / 阅读历史记录",
    },
    {
        "name": "annotations",
        "description": "Text annotations and highlights / 经文批注与标记",
    },
    {
        "name": "exports",
        "description": "Export texts in PDF, EPUB, and other formats / 导出经文为 PDF、EPUB 等格式",
    },
    {
        "name": "iiif",
        "description": "IIIF manifests for interoperable image delivery / IIIF 标准图像清单",
    },
    {
        "name": "stats",
        "description": "Platform statistics and timeline data / 平台统计数据与时间线",
    },
    {
        "name": "dianjin",
        "description": "Dianjin (典津) cross-platform ancient text federated search / 典津跨平台古籍联合检索",
    },
    {
        "name": "source-suggestions",
        "description": "Community-submitted data source suggestions / 社区数据源推荐",
    },
    {
        "name": "feedbacks",
        "description": "User feedback submission and management / 用户反馈",
    },
    {
        "name": "notifications",
        "description": "User notification management / 用户通知管理",
    },
    {
        "name": "admin",
        "description": "Admin dashboard and management (requires admin role) / 管理后台（需管理员权限）",
    },
    {
        "name": "sitemap",
        "description": "Dynamic XML sitemap for SEO / SEO 动态站点地图",
    },
    {
        "name": "rss",
        "description": "RSS 2.0 feed for recently added texts / RSS 订阅最新经文",
    },
]

app = FastAPI(
    title="FoJin API — Buddhist Digital Text Platform",
    description=_API_DESCRIPTION,
    version="3.0.0",
    lifespan=lifespan,
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    openapi_tags=_OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

_cors_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:5174"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)
app.add_middleware(RateLimitMiddleware)
# GZip handled by nginx — removed from backend to avoid compressing SSE streams


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s %d %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


class LastActiveMiddleware(BaseHTTPMiddleware):
    """Update user.last_active_at with 5-minute throttle."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only update for authenticated API requests
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer ") or not request.url.path.startswith("/api/"):
            return response

        try:
            from app.core.auth import verify_token
            token = auth_header[7:]
            user_id = verify_token(token)
            if user_id is None:
                return response

            redis_client = getattr(request.app.state, "redis", None)
            if redis_client is None:
                return response

            # 5-minute throttle via Redis
            key = f"last_active:{user_id}"
            if await redis_client.set(key, "1", nx=True, ex=300):
                from datetime import datetime

                from sqlalchemy import update

                from app.database import async_session
                from app.models.user import User

                async with async_session() as session:
                    await session.execute(
                        update(User)
                        .where(User.id == user_id)
                        .values(last_active_at=datetime.now(UTC))
                    )
                    await session.commit()
        except Exception:
            pass  # Never break request flow for activity tracking

        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(LastActiveMiddleware)


@app.exception_handler(FoJinError)
async def fojin_error_handler(request: Request, exc: FoJinError):
    http_exc = fojin_error_to_http(exc)
    return JSONResponse(
        status_code=http_exc.status_code,
        content={"detail": http_exc.detail},
    )


# Phase 1 routers
app.include_router(auth.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(texts.router, prefix="/api")
app.include_router(bookmarks.router, prefix="/api")
app.include_router(history.router, prefix="/api")

# Phase 2 routers
app.include_router(sources.router, prefix="/api")
app.include_router(relations.router, prefix="/api")
app.include_router(knowledge_graph.router, prefix="/api")
app.include_router(iiif.router, prefix="/api")

# Phase 3 routers
app.include_router(chat.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")

# Dictionary
app.include_router(dictionary.router, prefix="/api")

# Citations
app.include_router(citations.router, prefix="/api")

# Phase 4 routers
app.include_router(exports.router, prefix="/api")

# Dianjin (典津) cross-platform search — optional module
if dianjin is not None:
    app.include_router(dianjin.router, prefix="/api")

# Stats (dashboard + timeline)
app.include_router(stats.router, prefix="/api")

# Source suggestions (public)
app.include_router(source_suggestions.router, prefix="/api")

# Feedback
app.include_router(feedback.router, prefix="/api")

# Admin dashboard
app.include_router(admin.router, prefix="/api")

# Notifications
app.include_router(notification.router, prefix="/api")

# SEO: sitemap at root (no /api prefix)
app.include_router(sitemap.router)

# SEO: RSS feed at root (no /api prefix)
app.include_router(rss.router)


@app.get("/api/health")
async def health(request: Request):
    components: dict[str, str] = {}

    # Check Redis
    try:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client:
            await redis_client.ping()
            components["redis"] = "ok"
        else:
            components["redis"] = "not_configured"
    except (ConnectionError, OSError, Exception) as e:
        logger.warning("Health check: Redis error: %s", e)
        components["redis"] = "error"

    # Check PostgreSQL
    try:
        from sqlalchemy import text as sa_text
        async with async_engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
        components["postgresql"] = "ok"
    except (ConnectionError, OSError, Exception) as e:
        logger.warning("Health check: PostgreSQL error: %s", e)
        components["postgresql"] = "error"

    # Check Elasticsearch
    try:
        es = get_es()
        if es:
            await es.ping()
            components["elasticsearch"] = "ok"
        else:
            components["elasticsearch"] = "not_configured"
    except (ConnectionError, OSError, Exception) as e:
        logger.warning("Health check: Elasticsearch error: %s", e)
        components["elasticsearch"] = "error"

    all_ok = all(v == "ok" for v in components.values())
    status = "ok" if all_ok else "degraded"
    return {"status": status, **components}
