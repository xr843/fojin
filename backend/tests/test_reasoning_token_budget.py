"""Reasoning models spend part of max_tokens on hidden reasoning_content,
sharing the budget with the visible answer. A tight cap (the 30 used for
session titles) gets fully consumed by the reasoning trace → empty title /
truncated answer. These pin the detector + headroom helper. Audit 2026-06-23.
"""

from app.services.chat import _is_reasoning_model, _with_reasoning_headroom


def test_deepseek_v4_and_reasoners_detected():
    assert _is_reasoning_model("deepseek-v4-flash")
    assert _is_reasoning_model("deepseek-v4-pro")
    assert _is_reasoning_model("deepseek-reasoner")
    assert _is_reasoning_model("qwen3-thinking")


def test_non_reasoning_models_not_detected():
    for m in ("deepseek-chat", "qwen3.6-plus", "glm-5.1", "kimi-k2.6", "gpt-4o", "", None):
        assert not _is_reasoning_model(m)


def test_headroom_added_only_for_reasoning_models():
    # The title cap is the worst case: 30 tokens, fully eaten by reasoning.
    assert _with_reasoning_headroom("deepseek-v4-flash", 30) == 30 + 4000
    assert _with_reasoning_headroom("deepseek-v4-pro", 2000) == 2000 + 4000
    # Non-reasoning models keep the tight, cheap cap unchanged.
    assert _with_reasoning_headroom("deepseek-chat", 30) == 30
    assert _with_reasoning_headroom("glm-5.1", 2000) == 2000
