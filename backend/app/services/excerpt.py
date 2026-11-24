"""个人摘录：只有本人可读写。别人的摘录一律当作不存在（404），不泄露 id 是否有效。"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, TextNotFoundError, ValidationError
from app.models.excerpt import UserExcerpt
from app.models.text import BuddhistText
from app.schemas.excerpt import ExcerptCreate, ExcerptResponse

# 每人上限：正常读者远到不了，防脚本灌库。
MAX_EXCERPTS_PER_USER = 5000


def _to_response(ex: UserExcerpt, title_zh: str, cbeta_id: str) -> ExcerptResponse:
    return ExcerptResponse(
        id=ex.id,
        text_id=ex.text_id,
        title_zh=title_zh,
        cbeta_id=cbeta_id,
        juan_num=ex.juan_num,
        line_ref=ex.line_ref,
        end_line_ref=ex.end_line_ref,
        quote=ex.quote,
        note=ex.note,
        created_at=ex.created_at,
    )


def _clean_note(note: str | None) -> str | None:
    if note is None:
        return None
    note = note.strip()
    return note or None


async def list_excerpts(
    session: AsyncSession,
    user_id: int,
    *,
    text_id: int | None = None,
    juan_num: int | None = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    conds = [UserExcerpt.user_id == user_id]
    if text_id is not None:
        conds.append(UserExcerpt.text_id == text_id)
    if juan_num is not None:
        conds.append(UserExcerpt.juan_num == juan_num)
    total = (await session.execute(select(func.count()).select_from(UserExcerpt).where(*conds))).scalar() or 0
    # 阅读页按卷取（要按经文顺序高亮）；「我的摘录」页取全部（新的在前）。
    order = (
        (UserExcerpt.line_ref, UserExcerpt.id)
        if text_id is not None and juan_num is not None
        else (UserExcerpt.created_at.desc(), UserExcerpt.id.desc())
    )
    rows = (
        await session.execute(
            select(UserExcerpt, BuddhistText.title_zh, BuddhistText.cbeta_id)
            .join(BuddhistText, UserExcerpt.text_id == BuddhistText.id)
            .where(*conds)
            .order_by(*order)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_to_response(ex, title, cid) for ex, title, cid in rows],
    }


async def create_excerpt(session: AsyncSession, user_id: int, data: ExcerptCreate) -> ExcerptResponse:
    quote = data.quote.strip()
    if not quote:
        raise ValidationError("摘录内容不能为空")
    text = (await session.execute(select(BuddhistText).where(BuddhistText.id == data.text_id))).scalar_one_or_none()
    if text is None:
        raise TextNotFoundError(text_id=data.text_id)
    count = (
        await session.execute(select(func.count()).select_from(UserExcerpt).where(UserExcerpt.user_id == user_id))
    ).scalar() or 0
    if count >= MAX_EXCERPTS_PER_USER:
        raise ValidationError(f"摘录已达上限 {MAX_EXCERPTS_PER_USER} 条")
    ex = UserExcerpt(
        user_id=user_id,
        text_id=data.text_id,
        juan_num=data.juan_num,
        line_ref=data.line_ref,
        end_line_ref=data.end_line_ref,
        quote=quote,
        note=_clean_note(data.note),
    )
    session.add(ex)
    await session.commit()
    await session.refresh(ex)
    return _to_response(ex, text.title_zh, text.cbeta_id)


async def _owned(session: AsyncSession, user_id: int, excerpt_id: int) -> UserExcerpt:
    ex = (
        await session.execute(
            select(UserExcerpt).where(UserExcerpt.id == excerpt_id, UserExcerpt.user_id == user_id)
        )
    ).scalar_one_or_none()
    if ex is None:
        raise NotFoundError("摘录不存在")
    return ex


async def update_excerpt_note(
    session: AsyncSession, user_id: int, excerpt_id: int, note: str | None
) -> ExcerptResponse:
    ex = await _owned(session, user_id, excerpt_id)
    ex.note = _clean_note(note)
    await session.commit()
    await session.refresh(ex)
    text = (await session.execute(select(BuddhistText).where(BuddhistText.id == ex.text_id))).scalar_one()
    return _to_response(ex, text.title_zh, text.cbeta_id)


async def delete_excerpt(session: AsyncSession, user_id: int, excerpt_id: int) -> None:
    await _owned(session, user_id, excerpt_id)
    await session.execute(delete(UserExcerpt).where(UserExcerpt.id == excerpt_id, UserExcerpt.user_id == user_id))
    await session.commit()
