"""Tests for eval.from_feedback's sibling: estimated LLM cost accounting."""

from app.core import metrics
from app.services import llm_cost


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def test_estimate_cost_uses_model_price_then_default():
    # deepseek-v4-pro = 0.00087/1K over 2000 tokens = 0.00174
    assert llm_cost.estimate_cost_usd("deepseek-v4-pro", 1000, 1000) == 2000 / 1000 * 0.00087
    # Unknown model → DEFAULT_PRICE_PER_1K_USD
    assert llm_cost.estimate_cost_usd("who-knows", 1000, 0) == 1000 / 1000 * llm_cost.DEFAULT_PRICE_PER_1K_USD


def test_record_llm_cost_increments_tokens_and_cost_with_byok_label():
    tok = metrics.LLM_ESTIMATED_TOKENS_TOTAL
    cost = metrics.LLM_ESTIMATED_COST_USD_TOTAL

    p_before = _counter_value(tok, provider="deepseek", model="deepseek-v4-pro", byok="false", type="prompt")
    c_before = _counter_value(tok, provider="deepseek", model="deepseek-v4-pro", byok="false", type="completion")
    cost_before = _counter_value(cost, provider="deepseek", model="deepseek-v4-pro", byok="false")

    llm_cost.record_llm_cost(
        model="deepseek-v4-pro", provider="deepseek", is_byok=False,
        prompt_messages=[{"role": "user", "content": "问题"}, {"role": "system", "content": "系统"}],
        completion="这是回答",
    )

    prompt_tokens = llm_cost._estimate_tokens("问题系统")
    completion_tokens = llm_cost._estimate_tokens("这是回答")
    assert _counter_value(tok, provider="deepseek", model="deepseek-v4-pro", byok="false", type="prompt") == p_before + prompt_tokens
    assert _counter_value(tok, provider="deepseek", model="deepseek-v4-pro", byok="false", type="completion") == c_before + completion_tokens
    expected_cost = llm_cost.estimate_cost_usd("deepseek-v4-pro", prompt_tokens, completion_tokens)
    assert _counter_value(cost, provider="deepseek", model="deepseek-v4-pro", byok="false") == cost_before + expected_cost


def test_record_llm_cost_byok_true_label_is_separate():
    cost = metrics.LLM_ESTIMATED_COST_USD_TOTAL
    before = _counter_value(cost, provider="moonshot", model="kimi-k2.6", byok="true")
    llm_cost.record_llm_cost(
        model="kimi-k2.6", provider="moonshot", is_byok=True,
        prompt_messages=[{"role": "user", "content": "hi"}], completion="hello",
    )
    assert _counter_value(cost, provider="moonshot", model="kimi-k2.6", byok="true") > before


def test_record_llm_cost_never_raises_on_bad_input():
    # None provider, None completion, malformed messages must not raise.
    llm_cost.record_llm_cost(
        model="gpt-4o-mini", provider=None, is_byok=False,
        prompt_messages=[None, {"content": None}, "not-a-dict"], completion=None,
    )
