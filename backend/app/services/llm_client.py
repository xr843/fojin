"""LLM provider adapters and config resolution.

Extracted verbatim from ``app.services.chat`` (P1-3 god-file split):
provider URL/model tables, Anthropic wire-format adapters, reasoning-model
token headroom, BYOK error mapping, and primary/override/fallback config
resolution. NOTE: ``_build_llm_http_client`` deliberately stays in
``app.services.chat`` — tests patch ``app.services.chat.httpx`` to
intercept client construction, and moving it would silently break them.
"""

import logging

import httpx

from app.config import settings
from app.core.crypto import decrypt_api_key
from app.core.exceptions import ServiceError
from app.core.url_security import normalize_public_https_url
from app.models.user import User

logger = logging.getLogger(__name__)


PROVIDER_URLS = {
    # 国内
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "minimax": "https://api.minimax.chat/v1",
    "stepfun": "https://api.stepfun.com/v1",
    "baichuan": "https://api.baichuan-ai.com/v1",
    "yi": "https://api.lingyiwanwu.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    # 国际
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
}

# Provider → default model
PROVIDER_DEFAULT_MODELS = {
    # 国内
    "deepseek": "deepseek-v4-flash",
    "dashscope": "qwen3.6-plus",
    "zhipu": "glm-5.1",
    "moonshot": "kimi-k2.6",
    "doubao": "doubao-1.5-pro-32k",
    "minimax": "MiniMax-Text-01",
    "stepfun": "step-1-8k",
    "baichuan": "Baichuan4-Air",
    "yi": "yi-lightning",
    "siliconflow": "Qwen/Qwen2.5-7B-Instruct",
    # 国际
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "mistral": "mistral-small-latest",
    "xai": "grok-2-latest",
    "openrouter": "openai/gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
}

# Anthropic uses a different API format; detect by provider or URL
ANTHROPIC_API_VERSION = "2023-06-01"


def _is_anthropic(api_url: str, provider: str | None = None) -> bool:
    return provider == "anthropic" or "api.anthropic.com" in api_url


def _build_anthropic_headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }


def _convert_messages_for_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract system prompt and convert messages to Anthropic format."""
    system = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"] if not system else system + "\n\n" + m["content"]
        else:
            user_messages.append({"role": m["role"], "content": m["content"]})
    return system, user_messages


# Reasoning models (deepseek-v4*, deepseek-reasoner, *-thinking, o1/o3) emit
# hidden reasoning_content that shares the max_tokens budget with the visible
# answer. A tight cap — notably the 30 used for session titles — gets fully
# consumed by the reasoning trace, leaving content empty / answers truncated.
# bare "reasoner"/"thinking" are intentional broad substring matches (catch any
# provider's *-reasoner / *-thinking variant); "deepseek-v4" is explicit since
# its reasoning isn't reflected in the name.
_REASONING_MODEL_MARKERS = (
    "deepseek-v4", "reasoner", "thinking", "-o1", "-o3", "/o1", "/o3",
)


def _is_reasoning_model(model: str | None) -> bool:
    m = (model or "").lower()
    return any(k in m for k in _REASONING_MODEL_MARKERS)


def _with_reasoning_headroom(model: str | None, max_tokens: int) -> int:
    """Add budget for hidden reasoning_content on reasoning models so the
    visible answer isn't starved. max_tokens is a ceiling, not a target, so
    this is ~free for responses that don't hit the old cap — it only prevents
    reasoning from eating the entire short cap (empty titles) or truncating
    long answers."""
    return max_tokens + 4000 if _is_reasoning_model(model) else max_tokens


def _build_anthropic_body(model: str, messages: list[dict], *, temperature: float = 0.7,
                          max_tokens: int = 2000, stream: bool = False) -> dict:
    system, user_messages = _convert_messages_for_anthropic(messages)
    body: dict = {"model": model, "messages": user_messages, "temperature": temperature, "max_tokens": max_tokens}
    if system:
        body["system"] = system
    if stream:
        body["stream"] = True
    return body


def _byok_error_message(exc: Exception, status: int | None) -> str:
    """Map upstream BYOK errors to user-friendly Chinese messages.

    Many users see "API Key 无效或已过期" when the actual cause is a wrong
    model ID or insufficient balance — DashScope/DeepSeek/etc. tend to
    return 401/400/404 with descriptive bodies that we should surface.
    """
    body = ""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        try:
            body = exc.response.text[:600]
        except Exception:
            body = ""
    body_low = body.lower()

    # Model-not-found / model-not-authorized — most common foot-gun
    model_signals = ("model not found", "model_not_found", "modelnotfound", "no such model",
                     "does not exist", "not exist", "unsupported model", "invalid model",
                     "model 不存在", "模型不存在", "未开通", "无权访问")
    if any(sig in body_low for sig in (s.lower() for s in model_signals)):
        return "AI 服务返回：所选模型 ID 不存在或您的账号未开通该模型，请在个人中心检查「模型」字段（建议点击下方推荐预设）。"

    # Insufficient balance / quota
    balance_signals = ("insufficient balance", "insufficient_balance", "no balance",
                       "balance is insufficient", "quota exceeded", "out of credits",
                       "余额不足", "额度不足", "欠费", "余额")
    if any(sig in body_low for sig in (s.lower() for s in balance_signals)):
        return "AI 服务返回：您的 API 账户余额不足或额度耗尽，请前往服务商控制台充值。"

    # Auth failure — actual key invalid
    auth_signals = ("invalid api key", "invalid_api_key", "incorrect api key",
                    "authentication", "unauthorized", "api key 无效", "key 无效")
    if status == 401 and any(sig in body_low for sig in (s.lower() for s in auth_signals)):
        return "您的 API Key 无效或已过期，请在个人中心重新配置。"

    # Status-only fallbacks (couldn't recognize body, but status hints at cause)
    if status == 401:
        return "AI 服务返回 401（认证失败）：请检查个人中心 API Key 是否正确，或确认所选模型是否已开通。"
    if status == 404:
        return "AI 服务返回 404：所选模型 ID 不存在，请在个人中心检查「模型」字段（建议点击下方推荐预设）。"
    if status == 429:
        return "AI 服务返回 429：触发限流，请稍后重试或升级您的服务商套餐。"
    if status is not None:
        return f"AI 服务返回错误（HTTP {status}），请稍后重试或检查个人中心配置。"
    return "抱歉，AI 服务暂时不可用，请稍后重试。"


def _detect_model_from_url(api_url: str) -> str:
    """Infer a default model name from the API URL when LLM_MODEL is empty."""
    for provider, url in PROVIDER_URLS.items():
        if url in api_url or api_url in url:
            return PROVIDER_DEFAULT_MODELS[provider]
    return "gpt-4o-mini"


def _resolve_llm_config(user: User | None) -> tuple[str, str, str, bool, str]:
    """Return (api_url, api_key, model, is_byok, provider) based on user's BYOK or platform default."""
    if user and user.encrypted_api_key:
        try:
            key = decrypt_api_key(user.encrypted_api_key, user.api_key_kdf_version)
        except Exception as exc:
            logger.warning("Failed to decrypt user %s API key: %s", user.id, exc)
            raise ServiceError("您的 API Key 解密失败，请在个人中心重新配置。") from None

        provider = user.api_provider or "openai"
        if provider == "custom":
            try:
                url = normalize_public_https_url(user.api_custom_url, label="自定义 API 地址")
            except ValueError as exc:
                raise ServiceError(f"自定义 API 地址不安全：{exc}") from None
            model = user.api_model or "gpt-4o-mini"
        else:
            url = PROVIDER_URLS.get(provider, settings.llm_api_url)
            model = user.api_model or PROVIDER_DEFAULT_MODELS.get(provider, settings.llm_model)
        return url, key, model, True, provider
    url = settings.llm_api_url or "https://api.openai.com/v1"
    model = settings.llm_model or _detect_model_from_url(url)
    return url, settings.llm_api_key, model, False, "openai"


def _resolve_with_model_override(
    user: User | None, model_id: str | None
) -> tuple[str, str, str, bool, str]:
    """Same as _resolve_llm_config but allows a per-message model override.

    Selection precedence:
    1. model_id from request → look up CATALOG → if user has BYOK matching the
       same provider, use BYOK key with the catalog model. Else use platform
       key (only works for providers with a configured platform key —
       DeepSeek today).
    2. No model_id → fall back to _resolve_llm_config (BYOK or platform default).

    Raises ServiceError when model_id refers to a provider for which neither
    BYOK nor a platform key is available.
    """
    from app.services.llm_catalog import CATALOG_BY_ID  # local import to avoid cycle if any

    if not model_id:
        return _resolve_llm_config(user)
    opt = CATALOG_BY_ID.get(model_id)
    if not opt:
        # unknown id — silently fall back rather than 400, so a stale
        # localStorage value doesn't break chat
        logger.info("Unknown model_id %r from client; falling back to default", model_id)
        return _resolve_llm_config(user)
    # BYOK matching the catalog provider → use user's key, override model
    if user and user.encrypted_api_key:
        try:
            user_provider = user.api_provider or "openai"
            if user_provider == opt.provider:
                key = decrypt_api_key(user.encrypted_api_key, user.api_key_kdf_version)
                url = PROVIDER_URLS.get(opt.provider, settings.llm_api_url)
                return url, key, opt.model, True, opt.provider
        except Exception as exc:  # pragma: no cover — same handling as _resolve_llm_config
            logger.warning("Failed to decrypt user %s API key: %s", user.id, exc)
            raise ServiceError("您的 API Key 解密失败，请在个人中心重新配置。") from None
    # Platform path — only works when the platform-configured llm_api_url
    # matches this provider. Match by host prefix (rstrip trailing slashes)
    # to avoid false positives where one URL is a substring of another
    # (e.g. operator setting LLM_API_URL=https://api. would otherwise
    # match every provider).
    if _platform_provider_matches(opt.provider) and settings.llm_api_key:
        expected_url = PROVIDER_URLS[opt.provider]
        return expected_url, settings.llm_api_key, opt.model, False, opt.provider
    # Provider not available on platform; user has no matching BYOK
    raise ServiceError(
        f"所选模型「{opt.label}」需要在个人中心配置 {opt.provider} 服务商的 API Key 后使用。"
    )


def _platform_provider_matches(provider: str) -> bool:
    """True iff the platform-configured llm_api_url points at this provider.

    Uses host-anchored matching (after stripping trailing slashes) so that
    e.g. ``https://api.deepseek.com/v1`` and ``https://api.deepseek.com``
    both count as deepseek, but ``https://api.`` does not match every
    provider.
    """
    expected = PROVIDER_URLS.get(provider, "").rstrip("/")
    platform = (settings.llm_api_url or "").rstrip("/")
    if not expected or not platform:
        return False
    return platform == expected or platform.startswith(expected + "/") or expected.startswith(platform + "/")


def _resolve_fallback_llm_config() -> tuple[str, str, str, str] | None:
    """Platform fallback LLM, used only when the primary platform model fails
    before any tokens have been streamed. Returns (url, key, model, provider)
    or None if fallback is not configured. BYOK users never hit this path.
    """
    if not settings.llm_fallback_api_key:
        return None
    url = settings.llm_fallback_api_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = settings.llm_fallback_model or _detect_model_from_url(url)
    provider = "openai"
    for p, u in PROVIDER_URLS.items():
        if u in url or url in u:
            provider = p
            break
    return url, settings.llm_fallback_api_key, model, provider
