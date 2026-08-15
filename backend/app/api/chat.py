import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatAnswerDiagnostic, ChatAttachment, ChatMessage
from app.services.attachment_parser import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_BYTES,
    parse_attachment,
)

logger = logging.getLogger(__name__)

from app.config import settings
from app.core.client_ip import get_real_client_ip
from app.core.deps import get_current_user, get_optional_user
from app.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSource,
    ChatTrustStatus,
    FeedbackRequest,
    HotQuestionCard,
    HotQuestionCardsResponse,
    SessionListItem,
    SessionUpdateRequest,
)
from app.services.chat import (
    FREE_DAILY_LIMIT_ANONYMOUS,
    FREE_DAILY_LIMIT_USER,
    delete_session,
    get_anonymous_quota_used,
    get_history,
    get_history_paginated,
    get_hot_questions,
    get_random_hot_questions,
    get_session_for_user,
    list_sessions,
    send_message,
    send_message_stream,
    update_message_feedback,
    update_session,
)
from app.services.chat_trust import trust_status_from_diagnostic
from app.services.master_profiles import list_masters

router = APIRouter(prefix="/chat", tags=["chat"])


async def _trust_statuses_for_messages(
    db: AsyncSession,
    messages: list[ChatMessage],
) -> dict[int, ChatTrustStatus | None]:
    ids = [m.id for m in messages if m.role == "assistant"]
    if not ids:
        return {}
    result = await db.execute(
        select(ChatAnswerDiagnostic).where(ChatAnswerDiagnostic.message_id.in_(ids))
    )
    return {
        row.message_id: trust_status_from_diagnostic(row)
        for row in result.scalars().all()
    }


def _get_client_ip(request: Request) -> str:
    # Trust the LAST entry of X-Forwarded-For (appended by nginx); the
    # first entry is attacker-controlled. See app.core.client_ip docstring.
    return get_real_client_ip(request, default="unknown") or "unknown"


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
        text_id=data.text_id, juan_num=data.juan_num, selected_text=data.selected_text, page_content=data.page_content,
        hot_question_id=data.hot_question_id, model_id=data.model_id,
        attachment_ids=data.attachment_ids,
    )


@router.post("/stream")
async def chat_stream(
    request: Request,
    data: ChatRequest,
):
    """Stream AI answer via Server-Sent Events (SSE). Same as POST /chat but with real-time token streaming.

    SSE 流式发送消息并获取 AI 回答.

    Holds **no** request-scoped DB session. The endpoint takes neither
    ``Depends(get_db)`` nor ``Depends(get_optional_user)`` — the latter
    carries its own ``get_db`` yield-dependency, which FastAPI keeps checked
    out until the StreamingResponse body is fully sent, i.e. the entire
    60-120s LLM window, pinning a PG connection per active stream
    (project_fojin_db_pool_streaming). Instead the raw bearer token is read
    off the request and the user is resolved INSIDE the generator's
    short-lived prep session. The generator owns two short-lived sessions
    (prep + save) and holds none across the LLM I/O.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header[:7].lower() == "bearer " else None
    client_ip = _get_client_ip(request)
    redis = getattr(request.app.state, "redis", None)
    return StreamingResponse(
        send_message_stream(
            None, data.message, data.session_id, token=token,
            client_ip=client_ip, redis=redis, master_id=data.master_id,
            text_id=data.text_id, juan_num=data.juan_num, selected_text=data.selected_text, page_content=data.page_content,
            hot_question_id=data.hot_question_id, model_id=data.model_id,
            attachment_ids=data.attachment_ids,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
        },
    )


@router.post("/attachments", status_code=201)
async def upload_chat_attachment(
    file: UploadFile = File(...),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a single file (PDF/TXT/MD/DOCX/CSV/HTML, ≤10MB), parse to plain text,
    and return an attachment id the frontend can pass in chat send via attachment_ids.

    上传单个附件（PDF/TXT/MD/DOCX/CSV/HTML，≤10MB），解析为文本后返回附件 id。"""
    # Validation order follows CLAUDE.md HTTP code rule
    # (auth -> 415 -> 413 -> 422 -> 201). Auth is intentionally optional
    # since chat itself supports anonymous access; we skip the 401/403
    # bands entirely here.

    filename = file.filename or "upload"
    ext = ""
    idx = filename.rfind(".")
    if idx != -1:
        ext = filename[idx:].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="暂不支持该文件类型，可上传 PDF / TXT / MD / DOCX / CSV / HTML",
        )

    # Read in chunks so a malicious 1GB upload doesn't OOM the worker.
    # We bail the moment we cross MAX_FILE_BYTES — no need to read the
    # whole stream just to reject it.
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1 << 20  # 1 MiB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件超出 10 MB 上限",
            )
        chunks.append(chunk)
    file_bytes = b"".join(chunks)

    # Persist to disk first so the row always references a real file,
    # even if parse fails (we still want the parse_error trail).
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    disk_name = f"{uuid4().hex}{ext}"
    storage_path = str(upload_dir / disk_name)
    # Disk write and parse both run off the event loop: a 10MB PDF parse is
    # 200-500ms of pure-CPU pypdf/docx work and would otherwise freeze the
    # whole worker (stalling every concurrent request, including in-flight
    # /chat/stream) for the duration of one upload.
    try:
        await asyncio.to_thread(Path(storage_path).write_bytes, file_bytes)
    except OSError as exc:
        logger.exception("Failed to persist chat attachment to disk")
        raise HTTPException(status_code=500, detail=f"文件保存失败：{exc}") from exc

    parsed_text: str | None = None
    parse_error: str | None = None
    try:
        parsed_text = await asyncio.to_thread(
            parse_attachment, file_bytes, filename, file.content_type or ""
        )
    except ValueError as exc:
        parse_error = str(exc)[:500]
        logger.info("Attachment parse failed for %s: %s", filename, parse_error)
    except Exception as exc:  # pragma: no cover — safety net for unknown parser bugs
        parse_error = f"解析异常：{exc}"[:500]
        logger.exception("Unexpected parser error")

    row = ChatAttachment(
        user_id=user.id if user else None,
        filename=filename[:255],
        content_type=(file.content_type or "application/octet-stream")[:100],
        size_bytes=total,
        storage_path=storage_path[:500],
        parsed_text=parsed_text,
        parse_error=parse_error,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    if parse_error is not None:
        # Row is saved (so a future GC can clean the file), but the
        # request as a whole reports 422 so the frontend knows to warn
        # the user.  We still emit the id in the body so the client
        # can choose to attach it anyway (with the parse_error inlined
        # by the chat service).
        # The parse_error string in DB keeps the raw exc text for
        # debugging, but the user-facing detail is stripped to its
        # Chinese prefix to avoid leaking pypdf / docx internal
        # exception traces. Parser errors all use the form
        # "<friendly Chinese reason>：<library detail>".
        user_facing = parse_error.split("：", 1)[0] if "：" in parse_error else "文件解析失败"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"上传成功但解析失败：{user_facing}",
        )

    preview = (parsed_text or "")[:200]
    return {
        "id": row.id,
        "filename": row.filename,
        "size_bytes": row.size_bytes,
        "char_count": len(parsed_text or ""),
        "preview": preview,
    }


@router.get("/models", response_model=list[dict])
async def list_chat_models(
    user: User | None = Depends(get_optional_user),
):
    """Return curated catalog of selectable models, with availability flag.

    返回前端可选的精选模型列表（含可用性标记）。"""
    from app.services.chat import _platform_provider_matches
    from app.services.llm_catalog import CATALOG

    items = []
    for opt in CATALOG:
        # available if user BYOK matches OR platform key configured for this provider
        byok_ok = bool(
            user
            and user.encrypted_api_key
            and (user.api_provider or "openai") == opt.provider
        )
        platform_ok = bool(_platform_provider_matches(opt.provider) and settings.llm_api_key)
        items.append({
            "id": opt.id,
            "provider": opt.provider,
            "label": opt.label,
            "description": opt.description,
            "vision": opt.vision,
            "available": byok_ok or platform_ok,
            "requires_byok": not platform_ok,
        })
    return items


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

    获取当前用户或匿名用户的每日问答配额。

    ``authenticated`` exists because the two branches below are otherwise
    indistinguishable to the caller, and that ambiguity shipped a user-visible
    lie. ``get_optional_user`` returns ``None`` for a *missing* token and for an
    expired or otherwise invalid one alike (see ``resolve_optional_user``), so a
    logged-in reader whose 8-hour JWT had quietly expired fell through to the
    anonymous branch and was served ``limit: 10``. The client still had the user
    object in its persisted store, so it rendered the *logged-in* low-quota
    warning around the *anonymous* number — a reader with 199 of 200 questions
    left was told 10 remained. The same expiry silently demotes them on
    ``/chat/stream`` too (IP-shared quota, session not saved to their account),
    which is the part worth surfacing.

    With this flag the client can tell "you are a guest" from "your session
    expired" and say so, instead of inventing a quota."""
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
            "authenticated": True,
        }

    # Anonymous user — check Redis by IP. Also reached by a logged-in client
    # whose token expired; `authenticated: False` is the only signal that says
    # which of the two happened.
    client_ip = _get_client_ip(request)
    redis = getattr(request.app.state, "redis", None)
    used = await get_anonymous_quota_used(redis, client_ip)
    limit = FREE_DAILY_LIMIT_ANONYMOUS
    return {
        "limit": limit,
        "used": used,
        "remaining": limit - used,
        "has_byok": False,
        "authenticated": False,
    }


@router.get("/hot-questions")
async def hot_questions(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Legacy flat list used by the Tab-cycling suggestions.

    获取热门问题推荐列表（扁平列表，用于 Tab 建议补全）。"""
    redis = getattr(request.app.state, "redis", None)
    questions = await get_hot_questions(db, redis=redis)
    return {"questions": questions}


@router.get("/hot-questions/random", response_model=HotQuestionCardsResponse)
async def hot_questions_random(
    exclude_ids: str = Query(
        "",
        description="Comma-separated list of hot_question ids to avoid repeating.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Return one active question per category for the welcome cards.

    为首屏分类卡片各抽 1 条问题（白话翻译/经文解读/对比辨析/佛教史话），
    支持 exclude_ids 做同一次会话的去重轮换。"""
    parsed: list[int] = []
    for part in exclude_ids.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            parsed.append(int(part))
        except ValueError:
            continue
    rows = await get_random_hot_questions(db, exclude_ids=parsed or None)
    return HotQuestionCardsResponse(
        questions=[HotQuestionCard(**row) for row in rows]
    )


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
    trust_by_message = await _trust_statuses_for_messages(db, msgs)
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
                trust_status=trust_by_message.get(m.id),
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
    trust_by_message = await _trust_statuses_for_messages(db, msgs)
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
                trust_status=trust_by_message.get(m.id),
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
    trust_by_message = await _trust_statuses_for_messages(db, [msg])
    return ChatMessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        sources=[ChatSource(**s) for s in msg.sources] if msg.sources else None,
        trust_status=trust_by_message.get(msg.id),
        feedback=msg.feedback,
        created_at=msg.created_at,
    )


@router.patch("/sessions/{session_id}", response_model=SessionListItem)
async def patch_session(
    session_id: int,
    payload: SessionUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename and/or (un)pin a chat session.

    重命名 / 置顶会话。需要登录，且只能改自己的会话。"""
    return await update_session(
        db, session_id, user.id, title=payload.title, pinned=payload.pinned
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
