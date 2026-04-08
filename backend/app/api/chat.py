from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_optional_user
from app.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSource,
    FeedbackRequest,
    SessionListItem,
)
from app.services.chat import (
    FREE_DAILY_LIMIT_ANONYMOUS,
    FREE_DAILY_LIMIT_USER,
    delete_session,
    get_anonymous_quota_used,
    get_history,
    get_history_paginated,
    get_hot_questions,
    get_session_for_user,
    list_sessions,
    send_message,
    send_message_stream,
    update_message_feedback,
)
from app.services.master_profiles import list_masters

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("", response_model=ChatResponse)
async def chat(
    request: Request,
    data: ChatRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and receive an AI answer grounded in Buddhist texts (RAG). Supports BYOK and anonymous access.

    发送消息并获取基于经文的 AI 回答（支持自带 API Key 及匿名访问）。"""
    user_id = user.id if user else None
    client_ip = _get_client_ip(request) if not user else None
    redis = getattr(request.app.state, "redis", None)
    return await send_message(
        db, user_id, data.message, data.session_id, user=user,
        client_ip=client_ip, redis=redis, master_id=data.master_id,
        text_id=data.text_id, juan_num=data.juan_num, selected_text=data.selected_text,
    )


@router.post("/stream")
async def chat_stream(
    request: Request,
    data: ChatRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream AI answer via Server-Sent Events (SSE). Same as POST /chat but with real-time token streaming.

    SSE 流式发送消息并获取 AI 回答。"""
    user_id = user.id if user else None
    client_ip = _get_client_ip(request) if not user else None
    redis = getattr(request.app.state, "redis", None)
    return StreamingResponse(
        send_message_stream(
            db, user_id, data.message, data.session_id, user=user,
            client_ip=client_ip, redis=redis, master_id=data.master_id,
            text_id=data.text_id, juan_num=data.juan_num, selected_text=data.selected_text,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@router.get("/masters")
async def get_masters():
    """List available Buddhist master personas for the AI chat.

    获取可用的法师模式列表。"""
    return {"masters": list_masters()}


@router.get("/quota")
async def chat_quota(
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    """Get daily chat quota for the current user or anonymous visitor.

    获取当前用户或匿名用户的每日问答配额。"""
    from datetime import date

    if user:
        used = user.daily_chat_count if user.last_chat_date == date.today() else 0
        has_byok = bool(user.encrypted_api_key)
        limit = FREE_DAILY_LIMIT_USER
        return {
            "limit": limit,
            "used": used,
            "remaining": limit - used if not has_byok else -1,
            "has_byok": has_byok,
        }

    # Anonymous user — check Redis by IP
    client_ip = _get_client_ip(request)
    redis = getattr(request.app.state, "redis", None)
    used = await get_anonymous_quota_used(redis, client_ip)
    limit = FREE_DAILY_LIMIT_ANONYMOUS
    return {
        "limit": limit,
        "used": used,
        "remaining": limit - used,
        "has_byok": False,
    }


@router.get("/hot-questions")
async def hot_questions(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get recommended hot questions for the AI Q&A feature.

    获取热门问题推荐列表。"""
    redis = getattr(request.app.state, "redis", None)
    questions = await get_hot_questions(db, redis=redis)
    return {"questions": questions}


@router.get("/sessions", response_model=list[SessionListItem])
async def get_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all chat sessions for the authenticated user.

    获取当前用户的会话列表。需要登录。"""
    return await list_sessions(db, user.id)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get session details with full message history.

    获取会话详情及消息历史。"""
    cs = await get_session_for_user(db, session_id, user.id)
    msgs = await get_history(db, session_id)
    return ChatSessionResponse(
        id=cs.id,
        title=cs.title,
        created_at=cs.created_at,
        messages=[
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=[ChatSource(**s) for s in m.sources] if m.sources else None,
                feedback=m.feedback,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: int,
    page: int = 1,
    size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated session messages (page=1 returns the most recent messages).

    分页获取会话消息（page=1 为最新消息）。"""
    await get_session_for_user(db, session_id, user.id)
    msgs, total = await get_history_paginated(db, session_id, page, min(size, 100))
    return {
        "total": total,
        "page": page,
        "size": size,
        "messages": [
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=[ChatSource(**s) for s in m.sources] if m.sources else None,
                feedback=m.feedback,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    }


@router.put("/messages/{message_id}/feedback", response_model=ChatMessageResponse)
async def set_message_feedback(
    message_id: int,
    data: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rate an AI response (thumbs up / thumbs down / clear).

    对 AI 回答进行评价（点赞/点踩/取消）。"""
    msg = await update_message_feedback(db, message_id, user.id, data.feedback)
    return ChatMessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        sources=[ChatSource(**s) for s in msg.sources] if msg.sources else None,
        feedback=msg.feedback,
        created_at=msg.created_at,
    )


@router.delete("/sessions/{session_id}")
async def remove_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session and all its messages.

    删除会话及其所有消息。"""
    await delete_session(db, session_id, user.id)
    return {"ok": True}
