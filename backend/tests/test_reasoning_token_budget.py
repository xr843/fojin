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
    from app.services.llm_client import _REASONING_HEADROOM_TOKENS as H
    assert _with_reasoning_headroom("deepseek-v4-flash", 30) == 30 + H
    assert _with_reasoning_headroom("deepseek-v4-pro", 2000) == 2000 + H
    # Non-reasoning models keep the tight, cheap cap unchanged.
    assert _with_reasoning_headroom("deepseek-chat", 30) == 30
    assert _with_reasoning_headroom("glm-5.1", 2000) == 2000


def test_headroom_covers_a_reasoning_trace_actually_seen_in_production():
    """+4000 是 2026-06-23 针对**标题**（30 token 上限）定的，从没在「重推理模型
    + 完整 RAG 答案」上验证过。2026-08-01 生产实测把它打穿了：

    同一个问题（《地藏经》的孝道观与儒家有何不同？）、同一把 BYOK Key、同一端点，
    只换模型 ——
      deepseek-v4-pro    8 个推理事件、首字 11.2s、1,515 字、38s 完成
      deepseek-v4-flash  57–66 个推理事件、**11,826 字符的推理**、正文 0 字、
                         60–69s 后报「未能生成任何回答内容」

    11,826 字符按 _estimate_tokens 的 2/3 口径 ≈ 7,884 token，而当时的整个上限是
    2000+4000=6000 —— 推理独自就顶穿了天花板，模型被 length 截断，正文一个 token
    都没轮到。生产日志里另有一条 96.75s / 0 字符（session 2618）是同一回事。

    max_tokens 是天花板不是目标：调高它对推理少的模型（pro 只用约 1k）完全免费。
    """
    # 用实测到的那条推理轨迹作为下限，而不是拍一个好看的数字。
    observed_reasoning_tokens = 11826 * 2 // 3   # ≈ 7884
    answer_budget = 2000

    budget = _with_reasoning_headroom("deepseek-v4-flash", answer_budget)

    # 光够装下推理还不行 —— 装完推理必须还剩得下整段答案。
    assert budget >= observed_reasoning_tokens + answer_budget, (
        f"预算 {budget} 装不下实测的 {observed_reasoning_tokens} token 推理 + "
        f"{answer_budget} token 答案；这正是生产上 0 字回答的成因"
    )
