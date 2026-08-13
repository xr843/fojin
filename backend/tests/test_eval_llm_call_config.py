"""eval 的 LLM 调用参数必须能撑住重推理模型，否则它量的是空答案。

2026-08-13 在生产机上照抄 run_eval.py 当时的调用参数实跑（真实提示词、
deepseek-v4-pro、temperature 0）：

    timeout=60, max_tokens=2000  →  耗时 30.2s，**正文 0 字**，推理 2,686 字，
                                    finish=length

推理把 2000 token 的预算整个吃光，正文一个 token 都没轮到 —— 与 #1095 修掉的
生产故障是同一回事，只是这次躲在 eval 里。放宽后同一条提示词能正常出 1,000+ 字。

后果比一次线上故障更隐蔽：eval 不会报错，它会**给出一份 90 道题全是空答案的
报告**，引用准确性、幻觉率全归零，而我们会拿它去比较档位。

两条硬约束：

1. 预算要装得下「实测推理量 + 完整答案」，不能只按答案长度拍。
2. 超时要覆盖高档推理的实测总耗时（91.9s / 197.8s 两次），60 秒必然全军覆没。
"""

from eval.run_eval import EVAL_LLM_TIMEOUT_S, build_eval_llm_body

# 2026-08-13 生产实测的推理长度，取最大的那次当下限，不拍好看的数字。
MEASURED_REASONING_CHARS = 13908
# run_eval 与 chat 共用 _estimate_tokens 的 2/3 口径
MEASURED_REASONING_TOKENS = MEASURED_REASONING_CHARS * 2 // 3


def test_budget_survives_a_real_reasoning_trace():
    body = build_eval_llm_body("deepseek-v4-pro", [{"role": "user", "content": "x"}], 0.0)
    budget = body["max_tokens"]
    assert budget >= MEASURED_REASONING_TOKENS + 2000, (
        f"预算 {budget} 装不下实测的 {MEASURED_REASONING_TOKENS} token 推理 + 2000 token 答案；"
        "eval 会得到一份全是空答案的报告"
    )


def test_timeout_covers_measured_high_effort_latency():
    """高档推理实测总耗时 91.9s / 197.8s —— 60 秒会让 90 道题全部 [ERROR]。"""
    assert EVAL_LLM_TIMEOUT_S >= 240, (
        f"超时 {EVAL_LLM_TIMEOUT_S}s 低于实测的 197.8s 总耗时"
    )


def test_non_reasoning_model_budget_is_untouched():
    """非推理模型不该被顺手抬高预算 —— 那会改变既有基线的可比性。"""
    body = build_eval_llm_body("glm-5.2", [{"role": "user", "content": "x"}], 0.0)
    assert body["max_tokens"] == 2000


def test_thinking_effort_flows_into_the_eval_body(monkeypatch):
    """eval 必须能按档位跑，否则没法比较 high 与 low 的引用准确性。"""
    from app.services import llm_client

    monkeypatch.setattr(llm_client.settings, "chat_reasoning_effort", "low")
    body = build_eval_llm_body("deepseek-v4-pro", [{"role": "user", "content": "x"}], 0.0)
    assert body["reasoning_effort"] == "low"
    assert body["thinking"] == {"type": "enabled"}


def test_default_eval_body_sends_no_thinking_fields(monkeypatch):
    from app.services import llm_client

    monkeypatch.setattr(llm_client.settings, "chat_reasoning_effort", "")
    body = build_eval_llm_body("deepseek-v4-pro", [{"role": "user", "content": "x"}], 0.0)
    assert "thinking" not in body and "reasoning_effort" not in body
