from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user
from app.core.exceptions import TextNotFoundError
from app.database import get_db
from app.models.user import ReadingHistory, User
from app.schemas.text import JuanContentResponse, JuanLanguagesResponse, JuanListResponse, TextResponseBase
from app.services.content import get_juan_content, get_juan_languages, get_juan_list
from app.services.text import get_text_by_id, get_text_count

router = APIRouter(tags=["texts"])


@router.get("/texts/{text_id}", response_model=TextResponseBase)
async def get_text(text_id: int, db: AsyncSession = Depends(get_db)):
    """获取经典详情。"""
    text = await get_text_by_id(db, text_id)
    if not text:
        raise TextNotFoundError(text_id=text_id)
    return text


@router.get("/texts/{text_id}/juans", response_model=JuanListResponse)
async def list_juans(text_id: int, db: AsyncSession = Depends(get_db)):
    """获取经典的卷列表。"""
    result = await get_juan_list(db, text_id)
    if result is None:
        raise TextNotFoundError(text_id=text_id)
    return result


@router.get("/texts/{text_id}/juans/{juan_num}/languages", response_model=JuanLanguagesResponse)
async def juan_languages(text_id: int, juan_num: int, db: AsyncSession = Depends(get_db)):
    """获取某卷的可用语言列表。"""
    result = await get_juan_languages(db, text_id, juan_num)
    if result is None:
        raise TextNotFoundError(text_id=text_id)
    return result


@router.get("/texts/{text_id}/juans/{juan_num}", response_model=JuanContentResponse)
async def read_juan(
    text_id: int,
    juan_num: int,
    lang: str | None = Query(None, description="语言代码，如 pi、en、lzh"),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """获取经典某一卷的内容。登录用户自动记录阅读历史。"""
    result = await get_juan_content(db, text_id, juan_num, lang=lang)
    if result is None:
        raise TextNotFoundError(text_id=text_id)

    # Record reading history for logged-in users
    if user is not None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(ReadingHistory).values(
            user_id=user.id, text_id=text_id, juan_num=juan_num
        ).on_conflict_do_update(
            constraint="uq_reading_history_user_text",
            set_={"juan_num": juan_num, "last_read_at": datetime.now(UTC)},
        )
        await db.execute(stmt)
        await db.commit()

    return result


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """获取平台统计数据。"""
    count = await get_text_count(db)
    return {"total_texts": count}
