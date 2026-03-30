from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.role_guard import require_role
from app.database import get_db
from app.models.feedback import Feedback
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/feedbacks", tags=["feedbacks"])


class FeedbackCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    contact: str | None = Field(None, max_length=200)


class FeedbackResponse(BaseModel):
    id: int
    content: str
    contact: str | None
    status: str
    admin_reply: str | None = None
    replied_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminFeedbackItem(BaseModel):
    id: int
    user_id: int
    username: str
    content: str
    contact: str | None
    status: str
    admin_reply: str | None = None
    replied_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackReply(BaseModel):
    reply: str = Field(..., min_length=1, max_length=2000)


class AdminFeedbackListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[AdminFeedbackItem]


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|read|resolved)$")


# --- User endpoints ---


@router.post("", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    payload: FeedbackCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    feedback = Feedback(
        user_id=user.id,
        content=payload.content,
        contact=payload.contact,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


# --- Admin endpoints ---


@router.get("", response_model=AdminFeedbackListResponse)
async def list_feedbacks(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    base = select(Feedback, User.username).join(User, Feedback.user_id == User.id)
    count_base = select(func.count()).select_from(Feedback)

    if status:
        base = base.where(Feedback.status == status)
        count_base = count_base.where(Feedback.status == status)

    total = (await db.execute(count_base)).scalar_one()
    query = base.order_by(Feedback.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)

    items = []
    for fb, username in result.all():
        items.append(AdminFeedbackItem(
            id=fb.id,
            user_id=fb.user_id,
            username=username,
            content=fb.content,
            contact=fb.contact,
            status=fb.status,
            admin_reply=fb.admin_reply,
            replied_at=fb.replied_at,
            created_at=fb.created_at,
        ))
    return {"total": total, "page": page, "size": size, "items": items}


@router.patch("/{feedback_id}", response_model=FeedbackResponse)
async def update_feedback_status(
    feedback_id: int,
    payload: FeedbackStatusUpdate,
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")
    feedback.status = payload.status
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.post("/{feedback_id}/reply", response_model=FeedbackResponse)
async def reply_feedback(
    feedback_id: int,
    payload: FeedbackReply,
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")
    feedback.admin_reply = payload.reply
    feedback.replied_at = datetime.now(UTC)
    if feedback.status == "pending":
        feedback.status = "read"
    # 给用户发送站内通知
    notification = Notification(
        user_id=feedback.user_id,
        type="feedback_reply",
        title="您的反馈已收到回复",
        content=payload.reply,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.get("/pending-count")
async def get_pending_feedback_count(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count()).select_from(Feedback).where(Feedback.status == "pending")
    )
    return {"count": result.scalar_one()}
