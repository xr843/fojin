from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AccessDeniedError, NotFoundError, ValidationError
from app.models.annotation import Annotation


def _visible_to(viewer_id: int | None):
    """WHERE clause for annotations a viewer may see: approved ones are public;
    a signed-in viewer also sees their own (in any status). Anonymous sees only
    approved. Keeps other users' drafts/pending/rejected private."""
    if viewer_id is None:
        return Annotation.status == "approved"
    return or_(Annotation.status == "approved", Annotation.user_id == viewer_id)


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
    """Unfiltered lookup — used internally by update/delete/submit/review, which
    enforce their own ownership/role checks. Do NOT use for read endpoints; use
    get_visible_annotation so other users' non-approved rows stay private."""
    result = await session.execute(select(Annotation).where(Annotation.id == annotation_id))
    ann = result.scalar_one_or_none()
    if ann is None:
        raise NotFoundError("标注未找到")
    return ann


async def get_visible_annotation(
    session: AsyncSession, annotation_id: int, viewer_id: int | None = None
) -> Annotation:
    """Fetch a single annotation for a reader, enforcing visibility. Approved is
    public; the owner also sees their own. Anything else 404s (not 403, so we
    don't reveal that a hidden annotation exists)."""
    ann = await get_annotation(session, annotation_id)
    if ann.status != "approved" and ann.user_id != viewer_id:
        raise NotFoundError("标注未找到")
    return ann


async def list_annotations_for_text(
    session: AsyncSession, text_id: int, juan_num: int, viewer_id: int | None = None
) -> list[Annotation]:
    result = await session.execute(
        select(Annotation)
        .where(
            Annotation.text_id == text_id,
            Annotation.juan_num == juan_num,
            _visible_to(viewer_id),
        )
        .order_by(Annotation.start_pos)
    )
    return list(result.scalars().all())


async def update_annotation(
    session: AsyncSession, annotation_id: int, user_id: int, content: str | None = None
) -> Annotation:
    ann = await get_annotation(session, annotation_id)
    if ann.user_id != user_id:
        raise AccessDeniedError("无权修改")
    if content is not None:
        ann.content = content
    await session.commit()
    await session.refresh(ann)
    return ann


async def delete_annotation(session: AsyncSession, annotation_id: int, user_id: int) -> None:
    ann = await get_annotation(session, annotation_id)
    if ann.user_id != user_id:
        raise AccessDeniedError("无权删除")
    await session.delete(ann)
    await session.commit()


async def submit_annotation(session: AsyncSession, annotation_id: int, user_id: int) -> Annotation:
    """Submit a draft annotation for review (draft → pending)."""
    ann = await get_annotation(session, annotation_id)
    if ann.user_id != user_id:
        raise AccessDeniedError("无权提交")
    if ann.status != "draft":
        raise ValidationError(f"只有草稿状态的标注可以提交，当前状态: {ann.status}")
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
        raise ValidationError(f"只有待审核的标注可以审核，当前状态: {ann.status}")

    action_to_status = {
        "approve": "approved",
        "reject": "rejected",
        "request_change": "draft",
    }
    new_status = action_to_status.get(action)
    if new_status is None:
        raise ValidationError(f"无效的审核动作: {action}，可选: approve/reject/request_change")

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
