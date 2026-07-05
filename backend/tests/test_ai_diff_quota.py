"""AI-diff cost guard: rate limit + per-caller daily quota on fresh analyses.

/alignment/ai-diff stays public, but each cache-miss is a platform LLM call.
These tests pin that a fresh analysis consumes the daily budget (anonymous vs
signed-in limits), that cache hits are free, and that the endpoint is in
STRICT_PATHS.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import QuotaExceededError
from app.services.ai_diff import (
    FREE_DAILY_AI_DIFF_ANONYMOUS,
    FREE_DAILY_AI_DIFF_USER,
    _check_ai_diff_quota,
    get_or_create_diff,
)


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.fail = False

    async def incr(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key, ttl):
        return key in self.store


# ── _check_ai_diff_quota ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_anonymous_within_and_over_limit():
    r = FakeRedis()
    for _ in range(FREE_DAILY_AI_DIFF_ANONYMOUS):
        await _check_ai_diff_quota(r, "ip:1.2.3.4", is_authenticated=False)
    with pytest.raises(QuotaExceededError):
        await _check_ai_diff_quota(r, "ip:1.2.3.4", is_authenticated=False)


@pytest.mark.anyio
async def test_user_gets_higher_limit():
    r = FakeRedis()
    # Past the anonymous cap but still within the user cap → allowed.
    for _ in range(FREE_DAILY_AI_DIFF_ANONYMOUS + 5):
        await _check_ai_diff_quota(r, "user:7", is_authenticated=True)
    assert FREE_DAILY_AI_DIFF_USER > FREE_DAILY_AI_DIFF_ANONYMOUS


@pytest.mark.anyio
async def test_no_redis_is_noop():
    # Best-effort: without Redis the STRICT_PATHS rate limit is the backstop.
    await _check_ai_diff_quota(None, "ip:1.2.3.4", is_authenticated=False)


@pytest.mark.anyio
async def test_redis_error_allows():
    r = FakeRedis()
    r.fail = True
    await _check_ai_diff_quota(r, "ip:1.2.3.4", is_authenticated=False)  # no raise


# ── get_or_create_diff quota wiring ──────────────────────────────────────

@pytest.mark.anyio
async def test_cache_hit_does_not_consume_quota(monkeypatch):
    from app.services import ai_diff

    row = MagicMock()
    row.prompt_version = "v1"
    row.model = "m"
    row.analysis = {"summary": "s"}
    db = MagicMock()
    db.scalar = AsyncMock(return_value=row)  # cache hit

    called = {"quota": False, "llm": False}

    async def _quota(*a, **k):
        called["quota"] = True

    async def _llm(*a, **k):
        called["llm"] = True
        return {}

    monkeypatch.setattr(ai_diff, "_check_ai_diff_quota", _quota)
    monkeypatch.setattr(ai_diff, "_call_llm", _llm)

    cached, _, _, _ = await get_or_create_diff(db, [], redis=FakeRedis(), quota_identity="ip:x")
    assert cached is True
    assert called == {"quota": False, "llm": False}


@pytest.mark.anyio
async def test_cache_miss_checks_quota_before_llm(monkeypatch):
    from app.services import ai_diff

    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)  # cache miss

    order = []

    async def _quota(*a, **k):
        order.append("quota")

    async def _llm(*a, **k):
        order.append("llm")
        return {"summary": "s"}

    monkeypatch.setattr(ai_diff, "_check_ai_diff_quota", _quota)
    monkeypatch.setattr(ai_diff, "_call_llm", _llm)
    db.add = MagicMock()
    db.commit = AsyncMock()

    cached, _, _, _ = await get_or_create_diff(db, [], redis=FakeRedis(), quota_identity="ip:x")
    assert cached is False
    assert order == ["quota", "llm"]  # quota enforced before the paid call


@pytest.mark.anyio
async def test_cache_miss_quota_exceeded_blocks_llm(monkeypatch):
    from app.services import ai_diff

    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)

    async def _quota(*a, **k):
        raise QuotaExceededError(limit=FREE_DAILY_AI_DIFF_ANONYMOUS)

    llm_called = {"v": False}

    async def _llm(*a, **k):
        llm_called["v"] = True
        return {}

    monkeypatch.setattr(ai_diff, "_check_ai_diff_quota", _quota)
    monkeypatch.setattr(ai_diff, "_call_llm", _llm)

    with pytest.raises(QuotaExceededError):
        await get_or_create_diff(db, [], redis=FakeRedis(), quota_identity="ip:x")
    assert llm_called["v"] is False


def test_ai_diff_endpoint_is_strict_rate_limited():
    from app.core.rate_limit import STRICT_PATHS

    assert "/api/alignment/ai-diff" in STRICT_PATHS
