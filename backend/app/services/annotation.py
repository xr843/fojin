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
