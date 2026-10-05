"""阅读器「白话」：缓存、额度、失败即拒绝、请求形态。

上线门见 eval/vernacular/GATE.md；这里钉住的是服务契约——尤其「截断/空返回/
非 JSON 一律报错」：半句白话发给读者比不给更糟。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.exceptions import LLMServiceError, QuotaExceededError, TextNotFoundError
from app.core.rate_limit import STRICT_PATHS
from app.services import vernacular as v


class FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.counters: dict[str, int] = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, ttl):
        return True


def _db_with_text(text=None):
    db = AsyncMock()
    db.scalar.return_value = text
    return db


TEXT = SimpleNamespace(id=7, title_zh="金剛般若波羅蜜經", translator="鳩摩羅什")
ARGS = {"text_id": 7, "sentence": "過去心不可得，現在心不可得，未來心不可得。", "before": "前" * 100, "after": "後" * 100}


@pytest.mark.anyio
async def test_cache_miss_calls_llm_caches_and_consumes_quota():
    r = FakeRedis()
    with patch.object(v, "call_llm", AsyncMock(return_value=("過去的心不可得……", False))) as llm:
        out = await v.get_vernacular(_db_with_text(TEXT), redis=r, quota_identity="ip:1", **ARGS)
    assert out["translation"] == "過去的心不可得……" and out["cached"] is False
    assert out["model"] == v.resolve_model()
    llm.assert_awaited_once()
    assert sum(r.counters.values()) == 1
    assert len(r.kv) == 1


@pytest.mark.anyio
async def test_cache_hit_is_free_and_skips_llm():
    r = FakeRedis()
    with patch.object(v, "call_llm", AsyncMock(return_value=("译文", True))):
        await v.get_vernacular(_db_with_text(TEXT), redis=r, quota_identity="ip:1", **ARGS)
    with patch.object(v, "call_llm", AsyncMock()) as llm:
        out = await v.get_vernacular(_db_with_text(TEXT), redis=r, quota_identity="ip:1", **ARGS)
    llm.assert_not_awaited()
    assert out == {**out, "translation": "译文", "uncertain": True, "cached": True}
    assert sum(r.counters.values()) == 1  # 命中缓存不计额度


@pytest.mark.anyio
async def test_cache_key_ignores_far_context_but_not_near_context():
    m = "deepseek-v4-flash"
    base = v.cache_key(m, 7, "句", "遠" * 50 + "近" * 60, "近" * 60 + "遠" * 50)
    # 远处语境不同（选区边界不同）→ 同一条缓存
    assert base == v.cache_key(m, 7, "句", "別" * 50 + "近" * 60, "近" * 60 + "別" * 50)
    # 紧邻语境不同 → 不同缓存
    assert base != v.cache_key(m, 7, "句", "遠" * 50 + "異" * 60, "近" * 60 + "遠" * 50)
    # 提示词版本、模型、经 都进键
    assert base != v.cache_key("deepseek-v4-pro", 7, "句", "遠" * 50 + "近" * 60, "近" * 60 + "遠" * 50)


@pytest.mark.anyio
async def test_quota_exhausted_raises_before_llm():
    r = FakeRedis()
    r.counters[f"vern_quota:ip:1:{v.date.today().isoformat()}"] = v.FREE_DAILY_VERNACULAR_ANONYMOUS
    with patch.object(v, "call_llm", AsyncMock()) as llm, pytest.raises(QuotaExceededError):
        await v.get_vernacular(_db_with_text(TEXT), redis=r, quota_identity="ip:1", **ARGS)
    llm.assert_not_awaited()


@pytest.mark.anyio
async def test_unknown_text_404():
    with pytest.raises(TextNotFoundError):
        await v.get_vernacular(_db_with_text(None), redis=FakeRedis(), **ARGS)


def _transport(payload: dict, captured: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _completion(content: str, finish: str = "stop") -> dict:
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


async def _call_with(payload: dict, captured: list):
    real = httpx.AsyncClient

    def fake_client(*a, **kw):
        kw["transport"] = _transport(payload, captured)
        return real(*a, **kw)

    with patch.object(v.settings, "llm_api_key", "k"), patch.object(v.httpx, "AsyncClient", fake_client):
        return await v.call_llm("deepseek-v4-flash", "msg")


@pytest.mark.anyio
async def test_call_llm_parses_json_and_disables_thinking():
    captured: list = []
    out = await _call_with(_completion(json.dumps({"translation": "  白话  ", "uncertain": True})), captured)
    assert out == ("白话", True)
    body = captured[0]
    assert body["model"] == "deepseek-v4-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        _completion(json.dumps({"translation": "半句"}), finish="length"),  # 截断
        _completion("不是 JSON"),
        _completion(json.dumps({"translation": "   "})),  # 空译文
    ],
)
async def test_call_llm_rejects_truncated_or_malformed(payload):
    with pytest.raises(LLMServiceError):
        await _call_with(payload, [])


def test_endpoint_is_rate_limited():
    assert STRICT_PATHS.get("/api/reader/vernacular")


@pytest.mark.anyio
async def test_endpoint_rejects_overlong_sentence(client):
    resp = await client.post("/api/reader/vernacular", json={"text_id": 7, "sentence": "字" * 201})
    assert resp.status_code == 422
