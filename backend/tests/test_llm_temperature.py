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
