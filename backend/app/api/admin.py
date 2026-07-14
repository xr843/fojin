from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role_guard import require_role
from app.database import get_db
from app.models.annotation import Annotation
from app.models.feedback import Feedback
from app.models.source import SourceSuggestion
from app.models.user import User
from app.schemas.admin import (
    ActiveUserDayDetail,
    AdminAnnotationListResponse,
    AdminAuditLogListResponse,
    AdminModuleUsage,
    AdminOverview,
    AdminPendingSummary,
    AdminTrends,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserUpdate,
    AlignmentCoverageItem,
    AlignmentCoverageResponse,
    AnswerQueueResponse,
    AnswerReviewCreate,
    AnswerReviewResult,
    AnswerReviewStats,
)
from app.services.admin_service import (
    count_pending_candidates,
    count_pending_simple,
    daily_active_user_detail,
    get_overview,
    get_trends,
    list_annotations_for_review,
    list_audit_log,
    list_users,
    record_audit,
)
from app.services.alignment_coverage import compute_alignment_coverage
from app.services.answer_quality import (
    build_bad_answer_queue,
    count_unreviewed,
    review_stats,
    upsert_review,
)
from app.services.usage_service import get_module_usage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats/overview", response_model=AdminOverview)
async def stats_overview(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return await get_overview(db, redis)


@router.get("/alignment-coverage", response_model=AlignmentCoverageResponse)
async def alignment_coverage(
    limit: int = Query(200, ge=1, le=1000),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Per-lzh-text cross-canon alignment coverage, biggest-gap first — an ops
    view for deciding which sutra to align next. Admin-only."""
    items = await compute_alignment_coverage(db, limit=limit)
    return AlignmentCoverageResponse(
        items=[AlignmentCoverageItem(**it) for it in items],
        total=len(items),
    )


@router.get("/stats/trends", response_model=AdminTrends)
async def stats_trends(
    days: int = Query(30, ge=1, le=365),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    from app.main import app

    redis = getattr(app.state, "redis", None)
    return AdminTrends(**(await get_trends(db, days, redis)))


@router.get("/stats/active-users", response_model=ActiveUserDayDetail)
async def stats_active_users(
    date: date_cls = Query(..., description="Local-day (Asia/Shanghai) to break down, YYYY-MM-DD"),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Per-user breakdown of who was active (chatted or read) on a given day.

    Drill-down for the active-users trend point; not cached (admin-only, low
    volume, must reflect the live day)."""
    return ActiveUserDayDetail(**(await daily_active_user_detail(db, date)))


@router.get("/stats/module-usage", response_model=AdminModuleUsage)
async def stats_module_usage(
    days: int = Query(7, ge=1, le=90),
    _user=Depends(require_role("admin")),
):
    """Return Umami-sourced module usage stats (search / read / chat / source_click).

    This endpoint reads the self-hosted Umami analytics database.  It is fully
    resilient: if Umami is down or unreachable, it returns an empty result
    (events=[], top_search_keywords=[]) rather than propagating a 500 error.
    """
    result = await get_module_usage(days)
    return AdminModuleUsage(
        days=days,
        events=result["events"],
        top_search_keywords=result["top_search_keywords"],
        answer_quality=result["answer_quality"],
    )


@router.get("/users", response_model=AdminUserListResponse)
async def user_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|last_active_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_users(db, page, size, q, sort_by, sort_order)
    return {"total": total, "page": page, "size": size, "items": items}


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自己的角色或状态",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    changes: dict = {}
    if payload.role is not None and payload.role != user.role:
        changes["role"] = {"from": user.role, "to": payload.role}
        user.role = payload.role
    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = {"from": user.is_active, "to": payload.is_active}
        user.is_active = payload.is_active

    if changes:
        record_audit(
            db,
            actor_id=current_user.id,
            action="update_user",
            target_type="user",
            target_id=user.id,
            detail=changes,
        )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/annotations", response_model=AdminAnnotationListResponse)
async def annotation_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_annotations_for_review(db, page, size, status)
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/audit-log", response_model=AdminAuditLogListResponse)
async def audit_log_list(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    total, items = await list_audit_log(db, page, size, action)
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/answer-quality/queue", response_model=AnswerQueueResponse)
async def answer_quality_queue(
    window: int = Query(30, ge=1, le=365),
    min_suspicion: float = Query(0.0, ge=0.0),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """引用不可核对的回答队列(凭空引用 / 转述当原文引 / 引用被纠正 / 弱证据 /
    点踩 / 异常短)。只覆盖有诊断行的消息 —— 2026-07-01 之前的回答,坏引用的证据
    在入库时已被 verify_quoted_content 抹平,无法追溯。``tag_distribution`` 与
    ``score_distribution`` 用于校准阈值。"""
    return await build_bad_answer_queue(
        db,
        window_days=window,
        min_suspicion=min_suspicion,
        category=category,
        limit=limit,
        offset=offset,
    )


@router.post("/answer-quality/reviews", response_model=AnswerReviewResult)
async def answer_quality_review(
    payload: AnswerReviewCreate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Upsert the admin verdict for one assistant message (idempotent by
    message_id). Snapshots the detection reasons + score at review time."""
    try:
        remaining = await upsert_review(
            db,
            message_id=payload.message_id,
            verdict=payload.verdict,
            failure_category=payload.failure_category,
            note=payload.note,
            reviewed_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AnswerReviewResult(ok=True, remaining_unreviewed=remaining)


@router.get("/answer-quality/reviews/stats", response_model=AnswerReviewStats)
async def answer_quality_review_stats(
    window: int = Query(30, ge=1, le=365),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Labeled-dataset overview: reviewed totals + failure-category breakdown,
    windowed the same way as the queue (default 30 days) so the two numbers
    shown together on the admin page share one denominator."""
    return await review_stats(db, window_days=window)


@router.get("/pending-summary", response_model=AdminPendingSummary)
async def pending_summary(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """侧边栏角标。全部走 COUNT —— 不能在这里跑打分,导航每次都会读它。"""
    return AdminPendingSummary(
        answer_quality=await count_unreviewed(db),
        alignment_candidates=await count_pending_candidates(db),
        suggestions=await count_pending_simple(db, SourceSuggestion),
        feedbacks=await count_pending_simple(db, Feedback),
        annotations=await count_pending_simple(db, Annotation),
    )
