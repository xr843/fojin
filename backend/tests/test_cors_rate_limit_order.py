"""A rate-limited cross-origin request must still carry CORS headers.

RateLimitMiddleware used to sit outside CORSMiddleware, so its 429 went out
without Access-Control-Allow-Origin. The browser then cannot read the 429 (or
its Retry-After) and the fojin.ai page reported 「核对中断」 instead of waiting
(real Chrome, 2026-11-22, once the page called fojin.app directly). CORS must
wrap the rate limiter — which also keeps CORS preflights out of the budget."""

from fastapi.middleware.cors import CORSMiddleware

from app.core.rate_limit import RateLimitMiddleware


def test_cors_wraps_the_rate_limiter():
    from app.main import app

    order = [m.cls for m in app.user_middleware]  # index 0 = outermost
    assert order.index(CORSMiddleware) < order.index(RateLimitMiddleware)


def test_trace_limit_leaves_room_for_two_long_passages_a_minute():
    from app.config import settings
    from app.core.rate_limit import STRICT_PATHS
    from app.api.verification import TRACE_MAX_SENTENCES

    assert STRICT_PATHS["/api/verify/trace"] == settings.rate_limit_verify_trace
    # the page sends at most 40 sentences, 8 per call: two passages in a row = 10 calls
    assert settings.rate_limit_verify_trace * TRACE_MAX_SENTENCES >= 2 * 40
