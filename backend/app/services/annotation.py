from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation


async def create_annotation(
    session: AsyncSession,
    user_id: int,
    text_id: int,
    juan_num: int,
    start_pos: int,
    end_pos: int,
    annotation_type: str,
    content: str,
) -> Annotation:
    ann = Annotation(
        text_id=text_id,
        juan_num=juan_num,
        start_pos=start_pos,
        end_pos=end_pos,
        annotation_type=annotation_type,
        content=content,
        user_id=user_id,
        status="draft",
    )
    session.add(ann)
    await session.commit()
    await session.refresh(ann)
    return ann


async def get_annotation(session: AsyncSession, annotation_id: int) -> Annotation:
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    ann = result.scalar_one_or_none()
    if ann is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标注未找到")
    return ann


async def list_annotations_for_text(
    session: AsyncSession, text_id: int, juan_num: int
) -> list[Annotation]:
    result = await session.execute(
        select(Annotation)
        .where(Annotation.text_id == text_id, Annotation.juan_num == juan_num)
        .order_by(Annotation.start_pos)
    )
    return list(result.scalars().all())


async def update_annotation(
    session: AsyncSession, annotation_id: int, user_id: int, content: str | None = None
) -> Annotation:
    ann = await get_annotation(session, annotation_id)
    if ann.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改")
    if content is not None:
        ann.content = content
    await session.commit()
    await session.refresh(ann)
    return ann


async def delete_annotation(session: AsyncSession, annotation_id: int, user_id: int) -> None:
    ann = await get_annotation(session, annotation_id)
    if ann.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除")
    await session.delete(ann)
    await session.commit()


async def submit_annotation(session: AsyncSession, annotation_id: int, user_id: int) -> Annotation:
    """Submit a draft annotation for review (draft → pending)."""
    ann = await get_annotation(session, annotation_id)
    if ann.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权提交")
    if ann.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有草稿状态的标注可以提交，当前状态: {ann.status}",
        )
    ann.status = "pending"
    await session.commit()
    await session.refresh(ann)
    return ann


async def review_annotation(
    session: AsyncSession,
    annotation_id: int,
    reviewer_id: int,
    action: str,
    comment: str | None = None,
) -> Annotation:
    """Review a pending annotation (pending → approved/rejected/draft)."""
    from app.models.annotation import AnnotationReview

    ann = await get_annotation(session, annotation_id)
    if ann.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只有待审核的标注可以审核，当前状态: {ann.status}",
        )

    action_to_status = {
        "approve": "approved",
        "reject": "rejected",
        "request_change": "draft",
    }
    new_status = action_to_status.get(action)
    if new_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的审核动作: {action}，可选: approve/reject/request_change",
        )

    ann.status = new_status

    review = AnnotationReview(
        annotation_id=annotation_id,
        reviewer_id=reviewer_id,
        action=action,
        comment=comment,
    )
    session.add(review)

    await session.commit()
    await session.refresh(ann)
    return ann
