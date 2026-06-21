from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role_guard import require_role
from app.database import get_db
from app.models.user import User
from app.schemas.admin import (
    ActiveUserDayDetail,
    AdminAnnotationListResponse,
    AdminAuditLogListResponse,
    AdminModuleUsage,
    AdminOverview,
    AdminTrends,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserUpdate,
)
from app.services.admin_service import (
    daily_active_user_detail,
    get_overview,
    get_trends,
    list_annotations_for_review,
    list_audit_log,
    list_users,
    record_audit,
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
