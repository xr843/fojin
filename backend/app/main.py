from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.elasticsearch import close_es, init_es
from app.core.rate_limit import RateLimitMiddleware
from app.api import auth, bookmarks, history, search, texts
from app.api import sources, relations, knowledge_graph, iiif
from app.api import chat, annotations, exports, dictionary
from app.api import dianjin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await init_es()
    yield
    # Shutdown
    await app.state.redis.close()
    await close_es()


app = FastAPI(
    title="佛津 FoJin API",
    description="全球佛教古籍数字资源聚合平台",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

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

# Phase 4 routers
app.include_router(exports.router, prefix="/api")

# Dianjin (典津) cross-platform search
app.include_router(dianjin.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
