"""Chat session CRUD, history, feedback and deletion.

Extracted verbatim from ``app.services.chat`` (P1-3 god-file split).
Pure DB operations — no LLM, quota, or streaming concerns.
"""

import logging

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AccessDeniedError, NotFoundError, ValidationError
from app.models.chat import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


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

    count_result = await session.execute(
        select(func.count()).where(ChatMessage.session_id == session_id)
    )
    total = count_result.scalar() or 0

    # Page 1 = latest messages, page 2 = older, etc.
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    msgs = list(reversed(result.scalars().all()))  # reverse to chronological order
    return msgs, total



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
