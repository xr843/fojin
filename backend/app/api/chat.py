from fastapi import APIRouter, Depends
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
    SessionListItem,
)
from app.services.chat import (
    delete_session,
    get_history,
    get_session_for_user,
    list_sessions,
    send_message,
    send_message_stream,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """发送消息并获取 AI 回答（支持 BYOK）。"""
    user_id = user.id if user else None
    return await send_message(db, user_id, data.message, data.session_id, user=user)


@router.post("/stream")
async def chat_stream(
    data: ChatRequest,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式发送消息并获取 AI 回答。"""
    user_id = user.id if user else None
    return StreamingResponse(
        send_message_stream(db, user_id, data.message, data.session_id, user=user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@router.get("/quota")
async def chat_quota(
    user: User = Depends(get_current_user),
):
    """获取当前用户的每日问答配额。"""
    from datetime import date

    from app.services.chat import FREE_DAILY_LIMIT

    used = user.daily_chat_count if user.last_chat_date == date.today() else 0
    has_byok = bool(user.encrypted_api_key)
    return {
        "limit": FREE_DAILY_LIMIT,
        "used": used,
        "remaining": FREE_DAILY_LIMIT - used if not has_byok else -1,
        "has_byok": has_byok,
    }


@router.get("/sessions", response_model=list[SessionListItem])
async def get_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的会话列表。"""
    return await list_sessions(db, user.id)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取会话详情及消息历史。"""
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
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


@router.delete("/sessions/{session_id}")
async def remove_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除会话。"""
    await delete_session(db, session_id, user.id)
    return {"ok": True}
