from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.history import get_reading_history

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
async def list_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的阅读历史。"""
    return await get_reading_history(db, user.id, page, size)
