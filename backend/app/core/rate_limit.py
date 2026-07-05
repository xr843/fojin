"""Redis sliding window rate limiter middleware."""

import logging
import time

import redis.exceptions as redis_exc
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.client_ip import get_real_client_ip

logger = logging.getLogger(__name__)

# Stricter rate limits for sensitive/expensive endpoints (requests per minute)
STRICT_PATHS: dict[str, int] = {
    "/api/auth/login": settings.rate_limit_login,
    "/api/auth/register": settings.rate_limit_register,
    "/api/auth/change-password": 5,
    "/api/auth/sms/send-code": settings.rate_limit_sms_send,
    "/api/auth/sms/login": settings.rate_limit_sms_verify,
    "/api/search": 60,
    "/api/search/content": 30,
    # Paid-inference endpoints (embedding / LLM on the platform key).
    "/api/search/semantic": settings.rate_limit_semantic,
    "/api/research/query": settings.rate_limit_research,
    "/api/alignment/ai-diff": settings.rate_limit_ai_diff,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limit middleware based on client IP."""

    async def dispatch(self, request: Request, call_next):
        redis_client = getattr(request.app.state, "redis", None)
        if not redis_client:
            return await call_next(request)

        # Behind Nginx reverse proxy, request.client.host is always the
        # internal Docker IP. Use the shared helper to extract the real
        # client IP from X-Forwarded-For — taking the LAST entry, since
        # nginx's $proxy_add_x_forwarded_for appends the trusted on-the-wire
        # IP to any client-supplied value. Taking the first entry would
        # let clients forge their source IP and bypass rate limiting.
        client_ip = get_real_client_ip(request, default="unknown")
        path = request.url.path
        minute_window = int(time.time()) // 60

        # Determine rate limit for this path
        strict_limit = STRICT_PATHS.get(path)
        rate_limit = strict_limit if strict_limit is not None else settings.rate_limit_default

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
