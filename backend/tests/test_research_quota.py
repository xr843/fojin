"""Tests for the per-user daily research quota (wallet-DoS guard).

The research agent runs on the platform key and fans out into several paid
LLM + embedding calls per request, but /research/query had no quota — only
the per-IP default rate limit, which a proxy pool widens trivially. These
tests pin the per-user cap, BYOK exemption, and fail-closed-on-outage
behavior.
"""

import pytest

from app.core.exceptions import QuotaExceededError, ServiceError
from app.models.user import User
from app.services.chat_quota import (
    FREE_DAILY_LIMIT_RESEARCH,
    check_research_quota,
)


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}
        self.fail = False

    async def incr(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        return key in self.store


def _user(uid=1, byok=False):
    return User(id=uid, encrypted_api_key="enc" if byok else None)


@pytest.mark.anyio
async def test_within_limit_passes():
    r = FakeRedis()
    for _ in range(FREE_DAILY_LIMIT_RESEARCH):
        await check_research_quota(r, _user())  # must not raise


@pytest.mark.anyio
async def test_over_limit_raises_quota_exceeded():
    r = FakeRedis()
    for _ in range(FREE_DAILY_LIMIT_RESEARCH):
        await check_research_quota(r, _user())
    with pytest.raises(QuotaExceededError):
        await check_research_quota(r, _user())


@pytest.mark.anyio
async def test_byok_user_is_exempt():
    r = FakeRedis()
    # Way over the free limit, but BYOK pays their own key → never blocked.
    for _ in range(FREE_DAILY_LIMIT_RESEARCH * 3):
        await check_research_quota(r, _user(byok=True))
    assert r.store == {}  # counter never touched


@pytest.mark.anyio
async def test_quota_is_per_user():
    r = FakeRedis()
    for _ in range(FREE_DAILY_LIMIT_RESEARCH):
        await check_research_quota(r, _user(uid=1))
    # A different user still has their full budget.
    await check_research_quota(r, _user(uid=2))


@pytest.mark.anyio
async def test_fails_closed_when_redis_unavailable():
    with pytest.raises(ServiceError):
        await check_research_quota(None, _user())


@pytest.mark.anyio
async def test_fails_closed_on_redis_error():
    r = FakeRedis()
    r.fail = True
    with pytest.raises(ServiceError):
        await check_research_quota(r, _user())


def test_cost_endpoints_are_strict_rate_limited():
    from app.core.rate_limit import STRICT_PATHS

    assert "/api/research/query" in STRICT_PATHS
    assert "/api/search/semantic" in STRICT_PATHS
