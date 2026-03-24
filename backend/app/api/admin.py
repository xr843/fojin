from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role_guard import require_role
from app.database import get_db
from app.models.user import User
from app.schemas.admin import (
    AdminAnnotationListResponse,
    AdminOverview,
    AdminTrends,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserUpdate,
)
from app.services.admin_service import get_overview, get_trends, list_annotations_for_review, list_users

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats/overview", response_model=AdminOverview)
async def stats_overview(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return await get_overview(db)


@router.get("/stats/trends", response_model=AdminTrends)
async def stats_trends(
    days: int = Query(30, ge=1, le=365),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    return AdminTrends(**(await get_trends(db, days)))


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

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
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
