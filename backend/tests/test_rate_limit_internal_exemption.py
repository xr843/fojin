"""Internal (no-X-Forwarded-For) traffic must bypass the per-IP rate limiter.

The only public route to the backend is nginx, which always appends
X-Forwarded-For. Direct docker-network callers — the hosted fojin-mcp
container, compose healthchecks — carry no XFF and all share one internal
address, so keying them into the per-IP window would make every fojin-mcp
user worldwide share a single /api/search/semantic budget (20/min): the
hosted MCP endpoint would 429 itself to death on day one.
"""

from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.core.rate_limit import RateLimitMiddleware


class _FakeRedis:
    def __init__(self):
        self.incr_calls = 0

    async def incr(self, key):
        self.incr_calls += 1
        return 1

    async def expire(self, key, ttl):
        return True


def _request(headers: dict[str, str], redis) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/search/semantic",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
        "client": ("172.18.0.9", 40000),
        "app": SimpleNamespace(state=SimpleNamespace(redis=redis)),
    }
    return Request(scope)


async def _ok(_request):
    return PlainTextResponse("ok")


@pytest.mark.asyncio
async def test_no_xff_skips_rate_limiting():
    """No X-Forwarded-For ⇒ internal caller ⇒ no redis window consumed."""
    redis = _FakeRedis()
    mw = RateLimitMiddleware(app=None)
    resp = await mw.dispatch(_request({}, redis), _ok)
    assert resp.status_code == 200
    assert redis.incr_calls == 0


@pytest.mark.asyncio
async def test_xff_traffic_still_rate_limited():
    """Anything nginx forwarded keeps consuming its per-IP window."""
    redis = _FakeRedis()
    mw = RateLimitMiddleware(app=None)
    resp = await mw.dispatch(
        _request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}, redis), _ok
    )
    assert resp.status_code == 200
    assert redis.incr_calls == 1
