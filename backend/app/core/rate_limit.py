"""Redis sliding window rate limiter middleware."""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limit middleware based on client IP."""

    async def dispatch(self, request: Request, call_next):
        redis_client = getattr(request.app.state, "redis", None)
        if not redis_client:
            return await call_next(request)

        # Rate limit by client IP
        client_ip = request.client.host if request.client else "unknown"
        window_key = f"ratelimit:{client_ip}:{int(time.time()) // 60}"
        try:
            current = await redis_client.incr(window_key)
            if current == 1:
                await redis_client.expire(window_key, 120)  # 2 min TTL

            # Default rate limit: 200 requests/min per IP
            rate_limit = 200
            if current > rate_limit:
                return Response(
                    content='{"detail":"请求频率超限，请稍后再试"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )
        except Exception:
            pass  # Don't block on Redis errors

        response = await call_next(request)
        return response
