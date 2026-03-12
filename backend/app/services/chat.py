import logging
from datetime import date

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_api_key
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatResponse, ChatSource
from app.services.embedding import generate_embedding, similarity_search

logger = logging.getLogger(__name__)

# Free daily limit for users without their own API key
FREE_DAILY_LIMIT = 10

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
    "你是佛津（FoJin）佛教古籍智能助手。根据提供的佛典原文片段回答用户问题。"
    "回答时引用出处，如果提供的资料不足以回答，请如实告知。请使用用户的语言回答。"
    "你只回答与佛学、佛教文献、佛教历史和佛教文化相关的问题。如果用户提问与佛学无关，请礼貌地引导回佛学话题。"
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话未找到")
    if cs.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此会话")
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


def _resolve_llm_config(user: User | None) -> tuple[str, str, str, bool]:
    """Return (api_url, api_key, model, is_byok) based on user's BYOK or platform default."""
    if user and user.encrypted_api_key:
        try:
            key = decrypt_api_key(user.encrypted_api_key)
            provider = user.api_provider or "openai"
            url = PROVIDER_URLS.get(provider, settings.llm_api_url)
            model = user.api_model or PROVIDER_DEFAULT_MODELS.get(provider, settings.llm_model)
            return url, key, model, True
        except Exception:
            logger.warning("Failed to decrypt user %s API key, falling back to platform", user.id)
    return settings.llm_api_url, settings.llm_api_key, settings.llm_model, False


async def _check_daily_quota(db: AsyncSession, user: User) -> None:
    """Check and increment daily free chat quota. Raises HTTPException if exceeded."""
    today = date.today()
    if user.last_chat_date != today:
        user.daily_chat_count = 0
        user.last_chat_date = today
    if user.daily_chat_count >= FREE_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"今日免费额度已用完（{FREE_DAILY_LIMIT}次/天）。配置自己的 API Key 可无限使用。",
        )
    user.daily_chat_count += 1
    await db.flush()


async def send_message(
    db: AsyncSession,
    user_id: int | None,
    message: str,
    session_id: int | None = None,
    user: User | None = None,
) -> ChatResponse:
    # Validate message
    if not message or not message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息不能为空")
    if len(message) > 2000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息长度不能超过2000字")

    # Resolve LLM config (BYOK or platform)
    api_url, api_key, model, is_byok = _resolve_llm_config(user)

    # Check if platform has LLM configured (for non-BYOK users)
    if not is_byok and not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="平台 AI 服务暂未配置。请在个人中心配置自己的 API Key 使用 AI 问答功能。",
        )

    # Daily quota check for non-BYOK users
    if not is_byok and user:
        await _check_daily_quota(db, user)

    # Anonymous users cannot use chat
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请登录后使用 AI 问答功能")

    # Get or create session, with strict ownership check
    if session_id:
        chat_session = await get_session(db, session_id)
        if chat_session is None:
            chat_session = await create_session(db, user_id, title=message[:50])
        elif chat_session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此会话")
    else:
        chat_session = await create_session(db, user_id, title=message[:50])

    # RAG: generate embedding and search
    sources: list[ChatSource] = []
    context_text = ""
    try:
        query_embedding = await generate_embedding(message)
        search_results = await similarity_search(db, query_embedding, limit=5)
        sources = [ChatSource(**r) for r in search_results]
        context_text = "\n\n".join(
            f"[出处: 文本#{r['text_id']} 第{r['juan_num']}卷]\n{r['chunk_text']}"
            for r in search_results
        )
    except Exception:
        logger.exception("Embedding/search failed, proceeding without RAG context")

    # Build messages for LLM
    history = await get_history(db, chat_session.id)
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history[-10:]:
        llm_messages.append({"role": msg.role, "content": msg.content})

    if context_text:
        llm_messages.append({
            "role": "user",
            "content": f"参考以下佛典原文片段:\n\n{context_text}\n\n用户问题: {message}",
        })
    else:
        llm_messages.append({"role": "user", "content": message})

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
    except httpx.TimeoutException:
        logger.warning("LLM call timed out")
        answer = "抱歉，AI 服务响应超时，请稍后重试。"
    except httpx.HTTPStatusError as exc:
        logger.warning("LLM returned HTTP %s", exc.response.status_code)
        if is_byok and exc.response.status_code == 401:
            answer = "您的 API Key 无效或已过期，请在个人中心重新配置。"
        else:
            answer = f"抱歉，AI 服务返回错误（HTTP {exc.response.status_code}），请稍后重试。"
    except Exception:
        logger.exception("LLM call failed")
        answer = "抱歉，AI 服务暂时不可用，请稍后重试。"

    # Save messages
    user_msg = ChatMessage(session_id=chat_session.id, role="user", content=message)
    assistant_msg = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content=answer,
        sources=[s.model_dump() for s in sources] if sources else None,
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()

    return ChatResponse(
        session_id=chat_session.id,
        message=answer,
        sources=sources,
    )


async def delete_session(db: AsyncSession, session_id: int, user_id: int) -> None:
    cs = await get_session_for_user(db, session_id, user_id)
    # Bulk delete messages in a single statement
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await db.delete(cs)
    await db.commit()
