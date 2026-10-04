"""阅读器「白话」：选中一句，给出带标签的 AI 白话释义。

模型与提示词经 backend/eval/vernacular 评测过门才上线（见 GATE.md）：
默认 deepseek-v4-flash 关思考——n=40 盲评严重误译 1/40、p95 1.2 s；
默认思考档质量相近但 p95 53 s，不过延迟门。可用 settings.vernacular_model
切换（pro 关思考同样过门：严重 2/40、p95 2.7 s）。

结果按（提示词版本, 模型, 经, 选文, 近邻语境）缓存 30 天；只有缓存未命中才
消耗调用者的每日额度。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import LLMServiceError, QuotaExceededError, TextNotFoundError
from app.models.text import BuddhistText
from app.services.llm_client import thinking_params
from app.services.vernacular_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)

FREE_DAILY_VERNACULAR_ANONYMOUS = 30
FREE_DAILY_VERNACULAR_USER = 200
CACHE_TTL_SECONDS = 30 * 86400
# 缓存键只取紧邻选文的语境：同一句在不同选区边界下应命中同一条缓存
CACHE_CONTEXT_CHARS = 60


def resolve_model() -> str:
    return settings.vernacular_model or "deepseek-v4-flash"


def cache_key(model: str, text_id: int, sentence: str, before: str, after: str) -> str:
    payload = json.dumps(
        {
            "v": PROMPT_VERSION,
            "m": model,
            "t": text_id,
            "s": sentence,
            "b": before[-CACHE_CONTEXT_CHARS:],
            "a": after[:CACHE_CONTEXT_CHARS],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "vern:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _check_quota(redis, identity: str | None, is_authenticated: bool) -> None:
    """每日新生成额度。Redis 不可用时放行——STRICT_PATHS 的每分钟限流兜底。"""
    if redis is None or identity is None:
        return
    limit = FREE_DAILY_VERNACULAR_USER if is_authenticated else FREE_DAILY_VERNACULAR_ANONYMOUS
    key = f"vern_quota:{identity}:{date.today().isoformat()}"
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, 86400)
    except Exception:
        logger.warning("vernacular quota check failed; allowing", exc_info=True)
        return
    if current > limit:
        raise QuotaExceededError(limit=limit)


async def _cache_get(redis, key: str) -> dict | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
    except Exception:
        logger.warning("vernacular cache read failed", exc_info=True)
        return None
    return json.loads(raw) if raw else None


async def _cache_set(redis, key: str, value: dict) -> None:
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(value, ensure_ascii=False), ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("vernacular cache write failed", exc_info=True)


async def call_llm(model: str, user_msg: str) -> tuple[str, bool]:
    """单次非流式调用。返回 (译文, uncertain)。截断/空返回/非 JSON 一律视为失败，
    绝不把半句译文发给读者。"""
    if not settings.llm_api_key:
        raise LLMServiceError("白话释义未配置模型")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
        **thinking_params(model, "off"),
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.llm_api_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("vernacular LLM call failed: %r", e)
        raise LLMServiceError() from e

    choice = data["choices"][0]
    if choice.get("finish_reason") != "stop":
        logger.warning("vernacular LLM finish_reason=%s", choice.get("finish_reason"))
        raise LLMServiceError()
    try:
        parsed = json.loads(choice["message"].get("content") or "")
    except json.JSONDecodeError as e:
        logger.warning("vernacular LLM returned non-JSON")
        raise LLMServiceError() from e
    translation = str(parsed.get("translation") or "").strip()
    if not translation:
        raise LLMServiceError()
    return translation, bool(parsed.get("uncertain"))


async def get_vernacular(
    db: AsyncSession,
    *,
    text_id: int,
    sentence: str,
    before: str,
    after: str,
    redis=None,
    quota_identity: str | None = None,
    quota_is_authenticated: bool = False,
) -> dict:
    text = await db.scalar(select(BuddhistText).where(BuddhistText.id == text_id))
    if text is None:
        raise TextNotFoundError(text_id=text_id)

    model = resolve_model()
    key = cache_key(model, text_id, sentence, before, after)
    hit = await _cache_get(redis, key)
    if hit is not None:
        return {**hit, "cached": True}

    await _check_quota(redis, quota_identity, quota_is_authenticated)
    translation, uncertain = await call_llm(
        model,
        build_user_message(
            sentence=sentence,
            title=text.title_zh,
            translator=text.translator,
            before=before,
            after=after,
        ),
    )
    result = {
        "translation": translation,
        "uncertain": uncertain,
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
    await _cache_set(redis, key, result)
    return {**result, "cached": False}
