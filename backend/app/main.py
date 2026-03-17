import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

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
from app.api import (
    annotations,
    auth,
    bookmarks,
    chat,
    citations,
    dictionary,
    exports,
    history,
    iiif,
    knowledge_graph,
    relations,
    search,
    source_suggestions,
    sources,
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


app = FastAPI(
    title="佛津 FoJin API",
    description="全球佛教古籍数字资源聚合平台",
    version="3.0.0",
    lifespan=lifespan,
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
app.add_middleware(GZipMiddleware, minimum_size=1000)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        return response


app.add_middleware(SecurityHeadersMiddleware)


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

# Source suggestions (public)
app.include_router(source_suggestions.router, prefix="/api")


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
    except Exception:
        components["redis"] = "error"

    # Check PostgreSQL
    try:
        from sqlalchemy import text as sa_text
        async with async_engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
        components["postgresql"] = "ok"
    except Exception:
        components["postgresql"] = "error"

    # Check Elasticsearch
    try:
        es = get_es()
        if es:
            await es.ping()
            components["elasticsearch"] = "ok"
        else:
            components["elasticsearch"] = "not_configured"
    except Exception:
        components["elasticsearch"] = "error"

    all_ok = all(v == "ok" for v in components.values())
    status = "ok" if all_ok else "degraded"
    return {"status": status, **components}
