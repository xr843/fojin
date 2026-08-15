"""Invalidate the cached /api/sources payload.

失效 /api/sources 的列表缓存。

``GET /api/sources`` serves a Redis-cached payload with a 30-minute TTL. Two
writers change the underlying rows and only one of them used to clear the
cache: ``health_check_sources.py`` busts it after every run, but an **alembic
migration** — which is how data sources are actually added and edited in this
repo (see CLAUDE.md) — had no way to. The result was a source change landing in
Postgres and staying invisible to readers for up to 30 minutes, looking exactly
like a migration that silently failed to match any row.

``deploy.sh`` calls this right after ``alembic upgrade head``. Run it by hand
after any manual edit to ``data_sources``:

    cd backend
    python scripts/bust_sources_cache.py

Best-effort by design: a cache that cannot be reached is not a reason to fail a
deploy, since the TTL still expires on its own. Exit code is 0 unless the key
could not be deleted for an unexpected reason, in which case the caller may
ignore it — deploy.sh does.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis.asyncio as aioredis

from app.api.sources import SOURCES_LIST_CACHE_KEY
from app.config import settings


async def bust() -> int:
    """Delete the sources list cache key. Returns the number of keys removed."""
    client = aioredis.from_url(settings.redis_url)
    try:
        return await client.delete(SOURCES_LIST_CACHE_KEY)
    finally:
        await client.aclose()


def main() -> int:
    try:
        removed = asyncio.run(bust())
    except Exception as exc:  # best-effort; a dead cache must never break a deploy
        print(f"WARNING: could not invalidate '{SOURCES_LIST_CACHE_KEY}': {exc}")
        return 1
    if removed:
        print(f"Invalidated cache key '{SOURCES_LIST_CACHE_KEY}'.")
    else:
        # Nothing cached — the next reader rebuilds from Postgres either way.
        print(f"Cache key '{SOURCES_LIST_CACHE_KEY}' was not set; nothing to do.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
