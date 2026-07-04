"""Estimated LLM cost accounting for observability.

Chat never captures real token usage — the streaming path would need an
SSE-protocol change (``stream_options={"include_usage": True}`` + parsing a
usage chunk) to get exact counts. So spend is **estimated** from
``_estimate_tokens`` on the prompt + completion times a blended per-model
price, and emitted as Prometheus counters (see app/core/metrics.py). This is
order-of-magnitude — right for "is my bill trending up / which model dominates
/ how much is platform-paid vs BYOK", wrong for billing reconciliation.

The ``byok`` label is the one that matters operationally: ``byok="false"`` is
platform-paid spend (the operator's money); ``byok="true"`` is a user's own
key. Update ``PRICE_PER_1K_USD`` when provider pricing changes — it is a rough
mirror of ``scripts/build_alignments.LLM_PRICE_PER_1K``; keep the two aligned.
"""

from __future__ import annotations

import logging

from app.core.metrics import (
    LLM_ESTIMATED_COST_USD_TOTAL,
    LLM_ESTIMATED_TOKENS_TOTAL,
)
from app.services.prompt_builder import _estimate_tokens

logger = logging.getLogger(__name__)

# Blended $/1K tokens (input+output averaged — chat is output-heavy, so this
# tends to under-count for output-dominant turns; acceptable for trend/alert).
# Mirror of scripts/build_alignments.LLM_PRICE_PER_1K.
PRICE_PER_1K_USD: dict[str, float] = {
    "claude-haiku-4-5-20251001": 0.0008,
    "gpt-4o-mini": 0.00015,
    "qwen-plus": 0.0004,
    "qwen3.6-plus": 0.0004,
    "deepseek-chat": 0.00028,       # legacy alias → deepseek-v4-flash
    "deepseek-reasoner": 0.0014,    # legacy alias (thinking)
    "deepseek-v4-flash": 0.00028,
    "deepseek-v4-pro": 0.00087,
    "glm-5.1": 0.0006,
}
DEFAULT_PRICE_PER_1K_USD = 0.0008   # unknown model → Haiku-ish estimate


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Blended-price cost estimate for a single LLM call."""
    price = PRICE_PER_1K_USD.get(model, DEFAULT_PRICE_PER_1K_USD)
    return (prompt_tokens + completion_tokens) / 1000.0 * price


def record_llm_cost(
    *,
    model: str,
    provider: str | None,
    is_byok: bool,
    prompt_messages: list[dict] | None,
    completion: str | None,
) -> None:
    """Estimate and record the spend of one served chat LLM call.

    Never raises into the chat path — instrumentation must not break a reply.
    Call once per served call, at answer finalization, with the same
    ``model``/``provider``/``is_byok`` that actually served the request.
    """
    try:
        prompt_text = "".join(
            str(m.get("content", "")) for m in (prompt_messages or []) if isinstance(m, dict)
        )
        prompt_tokens = _estimate_tokens(prompt_text) if prompt_text else 0
        completion_tokens = _estimate_tokens(completion) if completion else 0

        labels_prov = provider or "unknown"
        byok = "true" if is_byok else "false"
        LLM_ESTIMATED_TOKENS_TOTAL.labels(labels_prov, model, byok, "prompt").inc(prompt_tokens)
        LLM_ESTIMATED_TOKENS_TOTAL.labels(labels_prov, model, byok, "completion").inc(
            completion_tokens
        )
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
        LLM_ESTIMATED_COST_USD_TOTAL.labels(labels_prov, model, byok).inc(cost)
    except Exception:  # pragma: no cover — defensive; must never break chat
        logger.warning("llm_cost: failed to record estimated spend", exc_info=True)
