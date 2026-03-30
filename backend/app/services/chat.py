import json
import logging
import time as _time
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_api_key
from app.core.exceptions import (
    AccessDeniedError,
    NotFoundError,
    QuotaExceededError,
    ServiceError,
    ValidationError,
)
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatResponse, ChatSource
from app.services.rag_retrieval import retrieve_rag_context

logger = logging.getLogger(__name__)

# Free daily limits for users without their own API key
FREE_DAILY_LIMIT_USER = 30       # Logged-in users
FREE_DAILY_LIMIT_ANONYMOUS = 10  # Anonymous users (encourage registration)

# Provider → base URL mapping
PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
}

# Provider → default model
PROVIDER_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "dashscope": "qwen-plus",
    "deepseek": "deepseek-chat",
    "siliconflow": "Qwen/Qwen2.5-7B-Instruct",
    "zhipu": "glm-4-flash",
}

SYSTEM_PROMPT = (
    "你是佛津（FoJin）佛教古籍智能助手。\n\n"
    "## 回答规则\n"
    "1. 基于提供的佛典原文片段回答用户问题，引用时使用格式：【《经名》第N卷】\n"
    "2. 如果提供的资料不足以回答，如实告知，不要编造内容\n"
    "3. 使用用户的语言回答\n"
    "4. 只回答佛学、佛教文献、佛教历史和佛教文化相关问题\n"
    "5. 非佛学问题请礼貌引导回佛学话题\n"
    "6. 每次回答结束后，另起一行输出 3 个递进式追问建议，格式严格如下：\n"
    "[追问] 问题1（深入当前回答的某个核心概念）\n"
    "[追问] 问题2（关联到相关经典或人物）\n"
    "[追问] 问题3（延伸到修行实践或现代意义）\n"
    "三个追问应形成由浅入深、从理论到实践的递进关系，引导用户逐步深入探索。\n"
    "7. 如果参考资料中包含[相关数据源推荐]，在回答末尾自然推荐相关数据源，"
    "格式如「您可以访问 XXX（链接）查阅相关资料」。如果没有数据源推荐则不提及。\n\n"
    "## 回答示例\n"
    "用户问：般若波罗蜜多心经的核心思想是什么？\n"
    "助手：《心经》的核心思想是「色不异空，空不异色」【《般若波罗蜜多心经》第1卷】，"
    "阐述了五蕴皆空的般若智慧。经文以「观自在菩萨，行深般若波罗蜜多时，照见五蕴皆空」开篇，"
    "揭示一切法的空性本质。\n\n"
    "[追问] 五蕴皆空具体指哪五蕴，各自含义是什么？\n"
    "[追问] 《心经》与《大般若经》六百卷是什么关系？\n"
    "[追问] 「色即是空」的智慧如何运用到日常修行中？"
)


async def create_session(session: AsyncSession, user_id: int | None, title: str | None = None) -> ChatSession:
    cs = ChatSession(user_id=user_id, title=title)
    session.add(cs)
    await session.commit()
    await session.refresh(cs)
    return cs


async def get_session(session: AsyncSession, session_id: int) -> ChatSession | None:
    result = await session.execute(select(ChatSession).where(ChatSession.id == session_id))
    return result.scalar_one_or_none()


async def get_session_for_user(session: AsyncSession, session_id: int, user_id: int) -> ChatSession:
    """获取会话并校验归属。user_id 必须匹配。"""
    cs = await get_session(session, session_id)
    if cs is None:
        raise NotFoundError("会话未找到")
    if cs.user_id != user_id:
        raise AccessDeniedError("无权访问此会话")
    return cs


async def list_sessions(session: AsyncSession, user_id: int) -> list[ChatSession]:
    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
    )
    return list(result.scalars().all())


async def get_history(session: AsyncSession, session_id: int) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def get_history_paginated(
    session: AsyncSession, session_id: int, page: int = 1, size: int = 50,
) -> tuple[list[ChatMessage], int]:
    """Return paginated messages (newest first page=1) and total count."""
    from sqlalchemy import func

    count_result = await session.execute(
        select(func.count()).where(ChatMessage.session_id == session_id)
    )
    total = count_result.scalar() or 0

    # Page 1 = latest messages, page 2 = older, etc.
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    msgs = list(reversed(result.scalars().all()))  # reverse to chronological order
    return msgs, total


def _detect_model_from_url(api_url: str) -> str:
    """Infer a default model name from the API URL when LLM_MODEL is empty."""
    for provider, url in PROVIDER_URLS.items():
        if url in api_url or api_url in url:
            return PROVIDER_DEFAULT_MODELS[provider]
    return "gpt-4o-mini"


def _resolve_llm_config(user: User | None) -> tuple[str, str, str, bool]:
    """Return (api_url, api_key, model, is_byok) based on user's BYOK or platform default."""
    if user and user.encrypted_api_key:
        try:
            key = decrypt_api_key(user.encrypted_api_key)
            provider = user.api_provider or "openai"
            url = PROVIDER_URLS.get(provider, settings.llm_api_url)
            model = user.api_model or PROVIDER_DEFAULT_MODELS.get(provider, settings.llm_model)
            return url, key, model, True
        except Exception as exc:
            logger.warning("Failed to decrypt user %s API key: %s", user.id, exc)
            raise ServiceError("您的 API Key 解密失败，请在个人中心重新配置。") from None
    url = settings.llm_api_url or "https://api.openai.com/v1"
    model = settings.llm_model or _detect_model_from_url(url)
    return url, settings.llm_api_key, model, False


async def _check_daily_quota(db: AsyncSession, user: User) -> None:
    """Check and increment daily free chat quota. Raises QuotaExceededError if exceeded."""
    today = date.today()
    if user.last_chat_date != today:
        user.daily_chat_count = 0
        user.last_chat_date = today
    if user.daily_chat_count >= FREE_DAILY_LIMIT_USER:
        raise QuotaExceededError(limit=FREE_DAILY_LIMIT_USER)
    user.daily_chat_count += 1
    await db.flush()


def _anon_quota_key(client_ip: str) -> str:
    """Redis key for anonymous daily chat quota by IP."""
    today = date.today().isoformat()
    return f"chat:anon:{client_ip}:{today}"


async def get_anonymous_quota_used(redis, client_ip: str) -> int:
    """Get the number of chats used today by an anonymous IP."""
    if not redis:
        return 0
    try:
        val = await redis.get(_anon_quota_key(client_ip))
        return int(val) if val else 0
    except Exception:
        return 0


async def _check_anonymous_quota(redis, client_ip: str) -> None:
    """Check and increment anonymous daily quota via Redis. Raises QuotaExceededError if exceeded."""
    if not redis:
        raise ServiceError("服务暂时不可用，请稍后重试")
    key = _anon_quota_key(client_ip)
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, 86400)  # 24h TTL
        if current > FREE_DAILY_LIMIT_ANONYMOUS:
            raise QuotaExceededError(limit=FREE_DAILY_LIMIT_ANONYMOUS)
    except QuotaExceededError:
        raise
    except Exception:
        logger.warning("Redis anonymous quota check failed", exc_info=True)


def _validate_message(message: str) -> None:
    """Validate chat message content."""
    if not message or not message.strip():
        raise ValidationError("消息不能为空")
    if len(message) > 2000:
        raise ValidationError("消息长度不能超过2000字")


async def _resolve_session(
    db: AsyncSession, user_id: int, message: str, session_id: int | None
) -> ChatSession:
    """Get or create a chat session, with ownership check."""
    if session_id:
        chat_session = await get_session(db, session_id)
        if chat_session is None:
            return await create_session(db, user_id, title=message[:50])
        if chat_session.user_id != user_id:
            raise AccessDeniedError("无权访问此会话")
        return chat_session
    return await create_session(db, user_id, title=message[:50])


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.5 chars per token for Chinese text."""
    return max(1, len(text) * 2 // 3)


# Reserve tokens for system prompt + output (max_tokens=2000)
_MAX_INPUT_TOKENS = 6000


def _build_llm_messages(
    history: list[ChatMessage], context_text: str, message: str
) -> list[dict[str, str]]:
    """Build the message list for the LLM call, trimming if too long."""
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    budget = _MAX_INPUT_TOKENS - _estimate_tokens(SYSTEM_PROMPT) - _estimate_tokens(message)

    # RAG context gets priority over history
    if context_text:
        ctx_tokens = _estimate_tokens(context_text)
        if ctx_tokens > budget * 0.6:
            # Truncate context to 60% of remaining budget
            max_chars = int(budget * 0.6 * 1.5)
            context_text = context_text[:max_chars]
            ctx_tokens = _estimate_tokens(context_text)
        budget -= ctx_tokens

    # Add as many recent history messages as budget allows
    trimmed_history = []
    for msg in reversed(history[-10:]):
        msg_tokens = _estimate_tokens(msg.content)
        if budget - msg_tokens < 0:
            break
        budget -= msg_tokens
        trimmed_history.append(msg)
    trimmed_history.reverse()

    for msg in trimmed_history:
        llm_messages.append({"role": msg.role, "content": msg.content})

    if context_text:
        llm_messages.append({
            "role": "user",
            "content": f"参考以下佛典原文片段:\n\n{context_text}\n\n用户问题: {message}",
        })
    else:
        llm_messages.append({"role": "user", "content": message})
    return llm_messages


def _strip_followup_suggestions(text: str) -> str:
    """Remove [追问] lines from the answer before persisting to DB."""
    lines = text.split("\n")
    cleaned = [line for line in lines if not line.strip().startswith("[追问]")]
    return "\n".join(cleaned).rstrip()


async def _save_messages(
    db: AsyncSession, session_id: int, message: str, answer: str, sources: list[ChatSource]
) -> None:
    """Persist user + assistant messages to the database."""
    user_msg = ChatMessage(session_id=session_id, role="user", content=message)
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=_strip_followup_suggestions(answer),
        sources=[s.model_dump() for s in sources] if sources else None,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()


async def _generate_session_title(
    api_url: str, api_key: str, model: str, message: str, answer: str,
) -> str | None:
    """Ask LLM to generate a short session title (5-10 chars). Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "用5-10个中文字概括以下对话的主题，只输出标题，不要标点符号。"},
                        {"role": "user", "content": f"用户问：{message[:100]}\n回答：{answer[:200]}"},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 30,
                },
            )
            resp.raise_for_status()
            title = resp.json()["choices"][0]["message"]["content"].strip().strip("\"'《》")
            return title[:30] if title else None
    except Exception:
        logger.debug("Failed to generate session title, keeping default")
        return None


async def _prepare_chat(
    db: AsyncSession,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
    client_ip: str | None = None,
    redis=None,
) -> tuple[ChatSession | None, str, str, str, bool, list[ChatSource], list[dict[str, str]]]:
    """Shared setup for send_message and send_message_stream.

    Returns (chat_session, api_url, api_key, model, is_byok, sources, llm_messages).
    chat_session is None for anonymous users.
    """
    _validate_message(message)

    # Resolve session first so ownership checks (403) come before config checks (503)
    chat_session = None
    if user_id is not None:
        chat_session = await _resolve_session(db, user_id, message, session_id)

    api_url, api_key, model, is_byok = _resolve_llm_config(user)

    if not is_byok and not api_key:
        raise ServiceError("平台 AI 服务暂未配置。请在个人中心配置自己的 API Key 使用 AI 问答功能。")

    if user_id is not None:
        if not is_byok:
            await _check_daily_quota(db, user)
    else:
        # Anonymous user — check IP-based quota via Redis
        if client_ip:
            await _check_anonymous_quota(redis, client_ip)

    # Fetch history first so we can use previous context for RAG retrieval
    history = await get_history(db, chat_session.id) if chat_session else []

    # Extract last user message from history for context-aware retrieval
    prev_user_msg = None
    for msg in reversed(history):
        if msg.role == "user":
            prev_user_msg = msg.content[:200]
            break

    # RAG: hybrid retrieval (context-aware with conversation history)
    sources, context_text = await retrieve_rag_context(db, message, prev_query=prev_user_msg)
    llm_messages = _build_llm_messages(history, context_text, message)

    return chat_session, api_url, api_key, model, is_byok, sources, llm_messages


async def send_message(
    db: AsyncSession,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
    client_ip: str | None = None,
    redis=None,
) -> ChatResponse:
    _t0 = _time.monotonic()
    chat_session, api_url, api_key, model, is_byok, sources, llm_messages = await _prepare_chat(
        db, user_id, message, session_id, user, client_ip=client_ip, redis=redis,
    )
    _t1 = _time.monotonic()
    logger.debug("TIMING: _prepare_chat took %.2fs", _t1 - _t0)

    # Call LLM
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": llm_messages,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"]
        logger.debug("TIMING: LLM call took %.2fs", _time.monotonic() - _t1)
    except httpx.TimeoutException:
        logger.warning("LLM call timed out")
        answer = "抱歉，AI 服务响应超时，请稍后重试。"
    except httpx.HTTPStatusError as exc:
        resp_body = exc.response.text[:500] if exc.response else "N/A"
        logger.warning("LLM returned HTTP %s: %s | url=%s model=%s", exc.response.status_code, resp_body, api_url, model)
        if is_byok and exc.response.status_code == 401:
            answer = "您的 API Key 无效或已过期，请在个人中心重新配置。"
        else:
            answer = f"抱歉，AI 服务返回错误（HTTP {exc.response.status_code}），请稍后重试。"
    except Exception:
        logger.exception("LLM call failed")
        answer = "抱歉，AI 服务暂时不可用，请稍后重试。"

    if chat_session:
        await _save_messages(db, chat_session.id, message, answer, sources)

        # Auto-generate a better session title for new sessions (first message)
        if chat_session.title == message[:50]:
            title = await _generate_session_title(api_url, api_key, model, message, answer)
            if title:
                chat_session.title = title
                await db.commit()

    return ChatResponse(
        session_id=chat_session.id if chat_session else 0,
        message=answer,
        sources=sources,
    )


async def send_message_stream(
    db: AsyncSession,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
    client_ip: str | None = None,
    redis=None,
):
    """Async generator yielding SSE events for streaming chat responses.

    Yields session_id immediately after validation so the frontend gets
    a response within milliseconds, then does RAG retrieval + LLM streaming.
    """
    # Flush Cloudflare's response buffer with a padded SSE comment (~2KB).
    yield ": " + " " * 2048 + "\n\n"

    # --- Phase 1: validation, quota, session, RAG (reuse _prepare_chat) ---
    try:
        chat_session, api_url, api_key, model, is_byok, sources, llm_messages = await _prepare_chat(
            db, user_id, message, session_id, user, client_ip=client_ip, redis=redis,
        )
    except (ValidationError, QuotaExceededError, AccessDeniedError, ServiceError) as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Yield session_id immediately so frontend gets a fast response
    yield f"data: {json.dumps({'type': 'session_id', 'session_id': chat_session.id if chat_session else 0}, ensure_ascii=False)}\n\n"

    # --- Phase 3: stream LLM ---
    full_answer = ""
    try:
        async with httpx.AsyncClient(timeout=60) as client, client.stream(
            "POST",
            f"{api_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": llm_messages,
                "temperature": 0.7,
                "max_tokens": 2000,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_answer += content
                        yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
    except httpx.TimeoutException:
        logger.warning("LLM stream timed out")
        error_msg = "抱歉，AI 服务响应超时，请稍后重试。"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
        full_answer = full_answer or error_msg
    except httpx.HTTPStatusError as exc:
        resp_body = exc.response.text[:500] if exc.response else "N/A"
        logger.warning("LLM stream returned HTTP %s: %s | url=%s model=%s", exc.response.status_code, resp_body, api_url, model)
        if is_byok and exc.response.status_code == 401:
            error_msg = "您的 API Key 无效或已过期，请在个人中心重新配置。"
        else:
            error_msg = f"抱歉，AI 服务返回错误（HTTP {exc.response.status_code}），请稍后重试。"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
        full_answer = full_answer or error_msg
    except Exception:
        logger.exception("LLM stream failed")
        error_msg = "抱歉，AI 服务暂时不可用，请稍后重试。"
        yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
        full_answer = full_answer or error_msg

    # Send sources after answer is complete, so citations appear below the text
    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': [s.model_dump() for s in sources]}, ensure_ascii=False)}\n\n"

    if chat_session:
        await _save_messages(db, chat_session.id, message, full_answer, sources)
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


DEFAULT_HOT_QUESTIONS = [
    "《心经》中「色不异空」的含义是什么？",
    "鸠摩罗什与玄奘的翻译风格有何不同？",
    "四圣谛的核心教义是什么？",
    "禅宗的「不立文字」思想源自哪些经典？",
]

HOT_QUESTIONS_CACHE_KEY = "chat:hot_questions"
HOT_QUESTIONS_CACHE_TTL = 3600  # 1 hour


async def get_hot_questions(db: AsyncSession, redis=None) -> list[str]:
    """Return top 8 most frequently asked questions from the last 7 days."""
    if redis:
        try:
            cached = await redis.get(HOT_QUESTIONS_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.debug("Failed to read hot questions cache", exc_info=True)

    since = datetime.now(UTC) - timedelta(days=7)
    stmt = (
        select(
            func.left(ChatMessage.content, 20).label("prefix"),
            func.min(ChatMessage.content).label("example"),
            func.count().label("cnt"),
        )
        .where(ChatMessage.role == "user", ChatMessage.created_at >= since)
        .group_by(func.left(ChatMessage.content, 20))
        .order_by(func.count().desc())
        .limit(8)
    )
    result = await db.execute(stmt)
    rows = result.all()
    questions = [row.example for row in rows if row.example and len(row.example.strip()) >= 4]

    if len(questions) < 4:
        seen = set(questions)
        for q in DEFAULT_HOT_QUESTIONS:
            if q not in seen:
                questions.append(q)
                seen.add(q)
            if len(questions) >= 8:
                break

    questions = questions[:8]

    if redis:
        try:
            await redis.set(HOT_QUESTIONS_CACHE_KEY, json.dumps(questions, ensure_ascii=False), ex=HOT_QUESTIONS_CACHE_TTL)
        except Exception:
            logger.debug("Failed to cache hot questions", exc_info=True)

    return questions


async def update_message_feedback(
    db: AsyncSession, message_id: int, user_id: int, feedback: str | None,
) -> ChatMessage:
    """Update feedback (up/down/null) for an assistant message owned by the user."""
    result = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    msg = result.scalar_one_or_none()
    if msg is None:
        raise NotFoundError("消息未找到")

    session = await get_session(db, msg.session_id)
    if session is None or session.user_id != user_id:
        raise AccessDeniedError("无权访问此消息")

    if msg.role != "assistant":
        raise ValidationError("只能对 AI 回答进行评价")

    msg.feedback = feedback
    await db.commit()
    await db.refresh(msg)
    return msg


async def delete_session(db: AsyncSession, session_id: int, user_id: int) -> None:
    cs = await get_session_for_user(db, session_id, user_id)
    # Bulk delete messages in a single statement
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.delete(cs)
    await db.commit()
