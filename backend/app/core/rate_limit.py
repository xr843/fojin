"""Redis sliding window rate limiter middleware."""

import logging
import time

import redis.exceptions as redis_exc
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Stricter rate limits for sensitive auth endpoints (requests per minute)
STRICT_PATHS: dict[str, int] = {
    "/api/auth/login": 10,
    "/api/auth/register": 5,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limit middleware based on client IP."""

    async def dispatch(self, request: Request, call_next):
        redis_client = getattr(request.app.state, "redis", None)
        if not redis_client:
            return await call_next(request)

        # Behind Nginx reverse proxy, request.client.host is always the
        # internal Docker IP. Read the real client IP from X-Forwarded-For
        # (set by Nginx: proxy_set_header X-Forwarded-For).
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # X-Forwarded-For: client, proxy1, proxy2 — take the first
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        minute_window = int(time.time()) // 60

        # Determine rate limit for this path
        strict_limit = STRICT_PATHS.get(path)
        rate_limit = strict_limit if strict_limit is not None else 200

        # Use path-specific key for strict paths to avoid sharing budget
        if strict_limit is not None:
            window_key = f"ratelimit:{client_ip}:{path}:{minute_window}"
        else:
            window_key = f"ratelimit:{client_ip}:{minute_window}"

        try:
            current = await redis_client.incr(window_key)
            if current == 1:
                await redis_client.expire(window_key, 120)  # 2 min TTL

            if current > rate_limit:
                return Response(
                    content='{"detail":"请求频率超限，请稍后再试"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )
        except (redis_exc.ConnectionError, redis_exc.TimeoutError, redis_exc.RedisError):
            logger.warning("Redis rate-limit check failed, allowing request", exc_info=True)

        response = await call_next(request)
        return response
