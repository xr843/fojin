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
    relations,
    search,
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
