"""Shared Redis cache helpers.

Small, dependency-free get/set wrappers around a Redis client that swallow
errors and serialize values as JSON. Extracted from feed_service /
stats_service / admin_service, which previously each carried a byte-identical
copy of these helpers (the only difference being a per-service default TTL,
which is now supplied explicitly by each caller).

The ``redis`` argument may be ``None`` (caching disabled), in which case
``cache_get`` returns ``None`` and ``cache_set`` is a no-op.
"""

import json
import logging
import random

logger = logging.getLogger(__name__)


def jittered_ttl(ttl: int, spread: float = 0.15) -> int:
    """Apply ±spread random jitter to a TTL.

    A batch of keys written in the same request/loop (e.g. the KG geo /
    lineage / stats / timeline caches, or a sweep of stats keys) would
    otherwise all expire on the same tick, so when a hot key lapses several
    concurrent requests miss together and stampede the expensive backing
    query at once. Spreading the expiry smooths that herd. Returns ≥1s.
    """
    delta = int(ttl * spread)
    if delta <= 0:
        return max(1, ttl)
    return max(1, ttl + random.randint(-delta, delta))  # nosec B311 — jitter, not crypto


async def cache_get(redis, key: str) -> dict | None:
    """Safely get and deserialize a cached value."""
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        if raw and isinstance(raw, str):
            return json.loads(raw)
    except Exception:
        logger.debug("Cache miss or error for key=%s", key)
    return None


async def cache_set(redis, key: str, value: dict, ttl: int) -> None:
    """Safely cache a serialized value with an explicit TTL (seconds)."""
    if redis is None:
        return
    try:
        await redis.setex(key, jittered_ttl(ttl), json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        logger.debug("Cache set error for key=%s", key)
