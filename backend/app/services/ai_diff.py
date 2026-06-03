"""Cross-canon AI difference analysis service.

Computes a deterministic cache key from the selected chunks + prompt
version + model so identical selections return cached analyses
verbatim. New analyses are produced by calling the server-side LLM
(settings.llm_api_url, OpenAI-compatible) with a locked system prompt.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_diff_cache import AiDiffCache
from app.schemas.ai_diff import AiDiffChunk
from app.services.ai_diff_prompt import PROMPT_VERSION, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def compute_chunks_hash(
    chunks: list[AiDiffChunk], prompt_version: str, model: str
) -> str:
    """Deterministic order-independent hash.

    We canonicalise chunks by sorting on (text_id, juan_num, chunk_index)
    then JSON-dumping with sorted keys, so equivalent selections produced
    in different orders share a cache row.
    """
    normalised = sorted(
        (
            {
                "text_id": c.text_id,
                "juan_num": c.juan_num,
                "chunk_index": c.chunk_index,
                "lang": c.lang,
                "text": c.text,
            }
            for c in chunks
        ),
        key=lambda c: (c["text_id"], c["juan_num"], c["chunk_index"]),
    )
    payload = json.dumps(
        {"chunks": normalised, "prompt_version": prompt_version, "model": model},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_or_create_diff(
    db: AsyncSession, chunks: list[AiDiffChunk]
) -> tuple[bool, str, str, dict[str, Any]]:
    """Return (cached, prompt_version, model, analysis).

    `cached=True` means the row was served from `ai_diff_cache`.
    `cached=False` means a fresh LLM call was made and the row was inserted.
    """
    model = _resolve_model()
    digest = compute_chunks_hash(chunks, PROMPT_VERSION, model)

    cached = await db.scalar(select(AiDiffCache).where(AiDiffCache.chunks_hash == digest))
    if cached is not None:
        return True, cached.prompt_version, cached.model, cached.analysis

    analysis = await _call_llm(chunks, model)

    row = AiDiffCache(
        chunks_hash=digest,
        prompt_version=PROMPT_VERSION,
        model=model,
        analysis=analysis,
    )
    db.add(row)
    await db.commit()
    return False, PROMPT_VERSION, model, analysis


def _resolve_model() -> str:
    """AI diff 的 model 决策 — 独立于 /chat 路径。

    deepseek-v4-pro / v4-flash 都是 reasoning models（像 o1），输出分为
    reasoning_tokens + content。结构化对照任务不需要推理，但 reasoning
    阶段会无差别消耗 max_tokens；2026-06-03 实测 max_tokens=1500 + v4-pro
    导致 reasoning_tokens 吃掉全部 budget、content="" 的空返回 bug。

    deepseek-chat 是 chat-only model（V3.x 系列），无 reasoning 阶段，
    适合结构化 JSON 输出。可用 settings.ai_diff_model 覆盖（保留切换通道）。
    """
    return getattr(settings, "ai_diff_model", None) or "deepseek-chat"


async def _call_llm(chunks: list[AiDiffChunk], model: str) -> dict[str, Any]:
    """Single non-streaming OpenAI-compatible chat.completions call.

    Returns the parsed JSON analysis object. Raises on HTTP error.
    """
    base = (settings.llm_api_url or "https://api.deepseek.com/v1").rstrip("/")
    key = settings.llm_api_key
    if not key:
        raise RuntimeError("ai_diff: settings.llm_api_key not configured")

    user_payload_lines = []
    for i, c in enumerate(chunks, 1):
        user_payload_lines.append(
            f"[版本 {i}] text_id={c.text_id} juan={c.juan_num} chunk={c.chunk_index} lang={c.lang}\n{c.text}"
        )
    user_msg = "\n\n".join(user_payload_lines)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{base}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

    raw = data["choices"][0]["message"]["content"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("ai_diff: LLM returned non-JSON content, wrapping as raw text")
        return {"summary": raw, "differences": [], "doctrinal_notes": ""}
