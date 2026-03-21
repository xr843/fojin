from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.role_guard import require_role
from app.database import get_db
from app.models.user import User
from app.schemas.annotation import AnnotationCreate, AnnotationResponse, AnnotationReviewCreate
from app.services.annotation import (
    create_annotation,
    delete_annotation,
    get_annotation,
    list_annotations_for_text,
    review_annotation,
    submit_annotation,
    update_annotation,
)

router = APIRouter(prefix="/annotations", tags=["annotations"])


@router.post("", response_model=AnnotationResponse)
async def create(
    data: AnnotationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建标注。"""
    return await create_annotation(
        db, user.id, data.text_id, data.juan_num,
        data.start_pos, data.end_pos, data.annotation_type, data.content,
    )


@router.get("", response_model=list[AnnotationResponse])
async def list_by_text(
    text_id: int = Query(...),
    juan_num: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    """获取指定文本卷的标注列表。"""
    return await list_annotations_for_text(db, text_id, juan_num)


@router.get("/{annotation_id}", response_model=AnnotationResponse)
async def get(
    annotation_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取标注详情。"""
    return await get_annotation(db, annotation_id)


@router.put("/{annotation_id}", response_model=AnnotationResponse)
async def update(
    annotation_id: int,
    data: AnnotationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新标注内容。"""
    return await update_annotation(db, annotation_id, user.id, content=data.content)


@router.post("/{annotation_id}/submit", response_model=AnnotationResponse)
async def submit(
    annotation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交标注审核（draft → pending）。"""
    return await submit_annotation(db, annotation_id, user.id)


@router.post("/{annotation_id}/review", response_model=AnnotationResponse)
async def review(
    annotation_id: int,
    data: AnnotationReviewCreate,
    user: User = Depends(require_role("admin", "reviewer")),
    db: AsyncSession = Depends(get_db),
):
    """审核标注（pending → approved/rejected/draft）。"""
    return await review_annotation(db, annotation_id, user.id, data.action, data.comment)


@router.delete("/{annotation_id}")
async def remove(
    annotation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除标注。"""
    await delete_annotation(db, annotation_id, user.id)
    return {"ok": True}
