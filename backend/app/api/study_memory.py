"""研读记忆：读者查看小津记得什么、改自己的回答偏好、整个关掉。只有本人可读写。"""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.schemas.study_memory import StudyMemoryResponse, StudyMemoryUpdate
from app.services.study_memory import build_study_memory, update_settings

router = APIRouter(prefix="/study-memory", tags=["study-memory"])


async def _current(db: AsyncSession, user_id: int) -> StudyMemoryResponse:
    mem = await build_study_memory(db, user_id)
    return StudyMemoryResponse(
        enabled=mem.enabled,
        notes=mem.notes,
        reading=[asdict(r) for r in mem.reading],
        topics=[asdict(t) for t in mem.topics],
        excerpts=[asdict(e) for e in mem.excerpts],
    )


@router.get("", response_model=StudyMemoryResponse)
async def get_study_memory(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _current(db, user.id)


@router.put("", response_model=StudyMemoryResponse)
async def put_study_memory(
    data: StudyMemoryUpdate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await update_settings(db, user.id, enabled=data.enabled, notes=data.notes)
    return await _current(db, user.id)
