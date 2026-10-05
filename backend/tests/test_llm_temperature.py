"""Tests for the Kimi Code coding-endpoint temperature handling (issue #1253).

The coding endpoint (api.kimi.com/coding/v1, membership-subscription keys)
rejects any temperature other than 1 with 400 "only 1 is allowed for this
model". We omit the field entirely for that provider — and for a "custom"
provider aimed at the same endpoint, which is the workaround users tried
before the preset existed.
"""
import pytest

from app.services.llm_client import openai_temperature_kwargs


@pytest.mark.parametrize(
    "provider,url",
    [
        ("kimi_code", "https://api.kimi.com/coding/v1"),
        ("kimi_code", "https://api.kimi.ai/coding/v1"),  # overseas mirror
        ("custom", "https://api.kimi.com/coding/v1"),    # custom provider aimed at the same endpoint
        ("custom", "https://api.kimi.com/coding/v1/"),   # trailing slash
    ],
)
def test_temperature_omitted_for_coding_endpoint(provider, url):
    assert openai_temperature_kwargs(provider, url, 0.7) == {}


@pytest.mark.parametrize(
    "provider,url",
    [
        ("moonshot", "https://api.moonshot.cn/v1"),
        ("custom", "https://api.moonshot.cn/v1"),
        ("openai", "https://api.openai.com/v1"),
        ("deepseek", "https://api.deepseek.com/v1"),
    ],
)
def test_temperature_kept_for_regular_providers(provider, url):
    assert openai_temperature_kwargs(provider, url, 0.7) == {"temperature": 0.7}


# ── 深度研究同样走用户自己的 Key，也得不携带 temperature ──────────────────


class _CapturingClient:
    """替身 httpx.AsyncClient：记下请求体，回一个最小的 chat/completions 响应。"""

    bodies: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, headers=None, json=None):
        import httpx

        _CapturingClient.bodies.append(json)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", url)
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "provider,url,expect_temperature",
    [
        ("kimi_code", "https://api.kimi.com/coding/v1", False),
        ("deepseek", "https://api.deepseek.com/v1", True),
    ],
)
async def test_research_agent_follows_the_same_temperature_rule(provider, url, expect_temperature):
    from unittest.mock import patch

    import httpx

    from app.services import llm_client
    from app.services.research_agent import build_research_agent

    _CapturingClient.bodies = []
    with (
        patch.object(llm_client, "_resolve_llm_config", return_value=(url, "sk-test", "some-model", True, provider)),
        patch.object(httpx, "AsyncClient", _CapturingClient),
    ):
        agent = build_research_agent(db=None, user=None)
        assert await agent._complete("system", "user") == "ok"
    assert len(_CapturingClient.bodies) == 1
    assert ("temperature" in _CapturingClient.bodies[0]) is expect_temperature
