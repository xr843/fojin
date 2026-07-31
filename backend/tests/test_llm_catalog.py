"""Tests for the curated LLM catalog and the per-message model override.

Guards two contracts:

1. ``CATALOG`` ids are stable and unique — frontend localStorage relies on
   these strings.
2. ``_resolve_with_model_override`` selects the right (url, key, model)
   triple based on BYOK vs platform availability, and falls back gracefully
   on unknown ids so a stale localStorage value never breaks chat.
"""

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ServiceError

# _resolve_* and their settings/decrypt_api_key collaborators live in
# llm_client after the P1-3 chat-service split; patch targets follow the code.
from app.services import llm_client as llm_module
from app.services.llm_catalog import CATALOG, CATALOG_BY_ID, DEFAULT_MODEL_ID
from app.services.llm_client import (
    PROVIDER_URLS,
    _resolve_llm_config,
    _resolve_with_model_override,
)


def test_catalog_ids_are_unique():
    ids = [opt.id for opt in CATALOG]
    assert len(ids) == len(set(ids)), "Duplicate ids in CATALOG"


def test_catalog_by_id_matches_catalog():
    assert set(CATALOG_BY_ID.keys()) == {opt.id for opt in CATALOG}


def test_default_model_id_is_in_catalog():
    assert DEFAULT_MODEL_ID in CATALOG_BY_ID


def test_resolve_with_no_model_id_falls_back_to_default(monkeypatch):
    """No model_id → behave exactly like _resolve_llm_config(user)."""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")
    monkeypatch.setattr(llm_module.settings, "llm_model", "deepseek-v4-pro")

    assert _resolve_with_model_override(None, None) == _resolve_llm_config(None)


def test_resolve_with_unknown_model_id_falls_back_gracefully(monkeypatch):
    """Stale localStorage id must not 400 — fall back to default."""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")
    monkeypatch.setattr(llm_module.settings, "llm_model", "deepseek-v4-pro")

    result = _resolve_with_model_override(None, "vendor:nonsense-model")
    assert result == _resolve_llm_config(None)


def test_resolve_platform_deepseek_pro(monkeypatch):
    """DeepSeek V4 Pro on platform key → returns deepseek URL + override model."""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")

    url, key, model, is_byok, provider = _resolve_with_model_override(None, "deepseek:v4-pro")
    assert url == PROVIDER_URLS["deepseek"]
    assert key == "platform-key"
    assert model == "deepseek-v4-pro"
    assert is_byok is False
    assert provider == "deepseek"


def test_resolve_platform_mismatch_raises(monkeypatch):
    """Platform configured as DeepSeek, user picks Moonshot, no BYOK → ServiceError."""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")

    with pytest.raises(ServiceError) as exc_info:
        _resolve_with_model_override(None, "moonshot:kimi-k3")
    # User-facing message must mention the provider so user knows which key to add
    assert "moonshot" in str(exc_info.value).lower() or "Kimi" in str(exc_info.value)


def test_resolve_byok_matching_provider_overrides_model(monkeypatch):
    """User has Moonshot BYOK, picks Moonshot model → use BYOK key + override model."""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")
    monkeypatch.setattr(
        llm_module, "decrypt_api_key", lambda blob, version=1: "user-moonshot-key"
    )

    user = MagicMock()
    user.id = 42
    user.encrypted_api_key = b"encrypted-blob"
    user.api_provider = "moonshot"
    user.api_model = "kimi-something-stale"

    url, key, model, is_byok, provider = _resolve_with_model_override(
        user, "moonshot:kimi-k3"
    )
    assert url == PROVIDER_URLS["moonshot"]
    assert key == "user-moonshot-key"
    assert model == "kimi-k3"
    assert is_byok is True
    assert provider == "moonshot"


def test_resolve_byok_provider_mismatch_falls_to_platform(monkeypatch):
    """User has Moonshot BYOK but picks DeepSeek → platform path (DeepSeek configured)."""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")

    user = MagicMock()
    user.id = 42
    user.encrypted_api_key = b"encrypted-blob"
    user.api_provider = "moonshot"

    url, key, model, is_byok, provider = _resolve_with_model_override(
        user, "deepseek:v4-pro"
    )
    assert url == PROVIDER_URLS["deepseek"]
    assert key == "platform-key"
    assert model == "deepseek-v4-pro"
    assert is_byok is False
    assert provider == "deepseek"


# ── DeepSeek V4 Flash（可选档，默认仍是 pro）─────────────────────────────

def test_flash_is_in_catalog_but_not_the_default():
    """加 flash 的整个前提就是"默认不变"——默认路径的答案质量要等 backend/eval
    的 90 题量出引用准确性与幻觉率的差之后再说。这条断言把这个前提钉住：
    有人手滑把 flash 挪到第一位、或改了 DEFAULT_MODEL_ID，这里立刻红。"""
    assert "deepseek:v4-flash" in CATALOG_BY_ID
    assert DEFAULT_MODEL_ID == "deepseek:v4-pro"
    assert CATALOG[0].id == "deepseek:v4-pro", "首项即默认（前端无 localStorage 时取它）"


def test_resolve_platform_deepseek_flash(monkeypatch):
    """flash 与 pro 同属 deepseek，平台已有的 Key 直接覆盖它 —— 加进目录就是
    所有人立刻可用，不需要任何人配 Key。"""
    monkeypatch.setattr(llm_module.settings, "llm_api_url", "https://api.deepseek.com/v1")
    monkeypatch.setattr(llm_module.settings, "llm_api_key", "platform-key")

    url, key, model, is_byok, provider = _resolve_with_model_override(None, "deepseek:v4-flash")
    assert url == PROVIDER_URLS["deepseek"]
    assert key == "platform-key"
    assert model == "deepseek-v4-flash"   # 上游真实模型名，不是目录 id
    assert is_byok is False
    assert provider == "deepseek"


def test_flash_counts_as_a_reasoning_model():
    """两个模型都支持思考模式。_REASONING_MODEL_MARKERS 里的 "deepseek-v4" 是
    子串匹配，所以 flash 自动落进推理分支 —— 推理额度与前端那条「正在推敲经文」
    的进度提示都靠它。若有人把标记收窄成精确匹配，这条会红。"""
    assert llm_module._is_reasoning_model("deepseek-v4-flash") is True
    assert llm_module._is_reasoning_model("deepseek-v4-pro") is True


def test_flash_gets_the_same_reasoning_headroom_as_pro():
    """推理模型会额外拿一份 headroom，免得隐藏推理把可见答案的额度吃光。
    flash 必须和 pro 拿到一样的待遇，否则长答案会被截断。"""
    assert llm_module._with_reasoning_headroom("deepseek-v4-flash", 2000) == \
           llm_module._with_reasoning_headroom("deepseek-v4-pro", 2000)
    assert llm_module._with_reasoning_headroom("deepseek-v4-flash", 2000) > 2000


def test_model_descriptions_carry_no_pricing():
    """描述是给读者选模型用的提示，不是价目表。摆价格在选择器里只会让人以为
    便宜的那个"缩水"了 —— 而两者规格其实相同。"""
    import re
    for opt in CATALOG:
        assert not re.search(r"价格|费用|元|/\s*3|便宜|免费", opt.description), \
            f"{opt.id} 的描述里出现了价格字样: {opt.description!r}"


# 目录与默认值可以不同档，但必须在这里登记理由 —— 空着的分歧一律视为"改了一处
# 忘了另一处"。登记项本身也会被校验：写了但实际相等，说明理由已过期。
INTENTIONAL_TIER_DIFFERENCES = {
    # 目录是"用户主动挑"的清单，给旗舰；默认值是"没挑时替他决定"，钱是用户自己
    # 出的，给经济档更稳妥。BYOK 用户没在选择器里指定模型时走的就是默认值。
    "openai": ("gpt-5.6-sol", "gpt-5.6-luna"),
    # 同理：Opus 是旗舰，Sonnet 是主力档。没主动挑模型的人不该被默认送进最贵的那档。
    "anthropic": ("claude-opus-5", "claude-sonnet-5"),
}


def test_catalog_and_provider_defaults_agree_on_generation():
    """同一个厂商的型号在 CATALOG（/chat 的选择器）与 PROVIDER_DEFAULT_MODELS
    （自带 Key 未指定模型时的默认）里各写一份。两处都在同一个仓、同一门语言里，
    只更新其中一处，自带 Key 的用户会拿到和界面上写的完全不同的模型。

    deepseek 不比：它在 CATALOG 里刻意有 pro/flash 两档，而默认值只能是一个。
    """
    from app.services.llm_client import PROVIDER_DEFAULT_MODELS

    for opt in CATALOG:
        if opt.provider == "deepseek":
            continue
        default = PROVIDER_DEFAULT_MODELS.get(opt.provider)
        expected = INTENTIONAL_TIER_DIFFERENCES.get(opt.provider)
        if expected:
            assert (opt.model, default) == expected, (
                f"{opt.provider} 登记了有意的档位差异 {expected}，但实际是 "
                f"({opt.model!r}, {default!r}) —— 版本变了就把登记项一起更新"
            )
            continue
        assert default == opt.model, (
            f"{opt.provider}: 选择器写的是 {opt.model!r}，"
            f"而 PROVIDER_DEFAULT_MODELS 写的是 {default!r}。"
            f"若这是有意的档位差异，请登记进 INTENTIONAL_TIER_DIFFERENCES 并写明理由"
        )


def test_registered_tier_differences_are_still_differences():
    """登记表里的项若已变成相等，说明那条理由过期了 —— 及时删掉，别让豁免长草。"""
    from app.services.llm_client import PROVIDER_DEFAULT_MODELS

    for provider, (cat, default) in INTENTIONAL_TIER_DIFFERENCES.items():
        assert cat != default, f"{provider} 的登记项两边相同，已无差异可豁免"
        assert PROVIDER_DEFAULT_MODELS.get(provider) == default


def test_one_entry_per_provider_except_deepseek():
    """「每个模型商只保留最新的一个旗舰模型」是这份目录的既定约定，deepseek 是
    有意的例外（pro/flash 同代两档）。多出来的条目应该是一次自觉的决定。"""
    from collections import Counter

    counts = Counter(opt.provider for opt in CATALOG)
    assert counts["deepseek"] == 2, "deepseek 应恰有 pro/flash 两档"
    for provider, n in counts.items():
        if provider != "deepseek":
            assert n == 1, f"{provider} 有 {n} 个条目，与目录约定不符"


def test_price_table_has_no_retired_models():
    """估价表的键是**上游模型名**。留着已下架的型号不会报错（未知模型退回默认价），
    但会让人以为覆盖率比实际更高 —— 而真正在跑的新模型反倒在吃默认估价。
    这里只钉住已确认下架/被取代的那几个。"""
    from app.services.llm_cost import PRICE_PER_1K_USD

    retired = {"qwen3.6-plus", "glm-5.1", "kimi-k2.6", "kimi-k2", "moonshot-v1-8k"}
    leftover = retired & PRICE_PER_1K_USD.keys()
    assert not leftover, f"估价表里仍留着已下架的型号: {sorted(leftover)}"


def test_provider_defaults_are_not_retired_models():
    """PROVIDER_DEFAULT_MODELS 是自带 Key 用户没指定模型时真正发出去的字符串。
    指向已下架型号的后果不是"退回上一代"，是那位用户直接 model not found。"""
    from app.services.llm_client import PROVIDER_DEFAULT_MODELS

    retired = {
        "qwen3.6-plus", "glm-5.1", "kimi-k2.6",      # 本次同步前的旧值
        "gpt-4o-mini", "claude-sonnet-4-20250514",   # 国际两家的旧值
    }
    bad = {p: m for p, m in PROVIDER_DEFAULT_MODELS.items() if m in retired}
    assert not bad, f"这些厂商的默认模型已下架/被取代: {bad}"
