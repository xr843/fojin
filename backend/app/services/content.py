from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import BuddhistText, TextContent
from app.schemas.text import JuanContentResponse, JuanInfo, JuanLanguagesResponse, JuanListResponse


async def get_juan_list(session: AsyncSession, text_id: int) -> JuanListResponse | None:
    """Get list of juans for a text."""
    result = await session.execute(select(BuddhistText).where(BuddhistText.id == text_id))
    bt = result.scalar_one_or_none()
    if bt is None:
        return None

    result = await session.execute(
        select(TextContent.juan_num, TextContent.char_count)
        .where(TextContent.text_id == text_id, TextContent.lang == bt.lang)
        .order_by(TextContent.juan_num)
    )
    rows = result.all()
    # Fallback: if no content in default lang, list all distinct juans
    if not rows:
        result = await session.execute(
            select(TextContent.juan_num, TextContent.char_count)
            .where(TextContent.text_id == text_id)
            .distinct(TextContent.juan_num)
            .order_by(TextContent.juan_num)
        )
        rows = result.all()

    return JuanListResponse(
        text_id=text_id,
        title_zh=bt.title_zh,
        total_juans=len(rows),
        juans=[JuanInfo(juan_num=r[0], char_count=r[1]) for r in rows],
    )


async def get_juan_languages(session: AsyncSession, text_id: int, juan_num: int) -> JuanLanguagesResponse | None:
    """Get available languages for a specific juan."""
    result = await session.execute(select(BuddhistText).where(BuddhistText.id == text_id))
    bt = result.scalar_one_or_none()
    if bt is None:
        return None

    result = await session.execute(
        select(TextContent.lang)
        .where(TextContent.text_id == text_id, TextContent.juan_num == juan_num)
        .distinct()
    )
    languages = [r[0] for r in result.all()]
    if not languages:
        return None

    return JuanLanguagesResponse(
        text_id=text_id,
        juan_num=juan_num,
        languages=languages,
        default_lang=bt.lang,
    )


async def get_juan_content(
    session: AsyncSession, text_id: int, juan_num: int, lang: str | None = None
) -> JuanContentResponse | None:
    """Get content of a specific juan, optionally filtered by language."""
    result = await session.execute(select(BuddhistText).where(BuddhistText.id == text_id))
    bt = result.scalar_one_or_none()
    if bt is None:
        return None

    query = select(TextContent).where(TextContent.text_id == text_id, TextContent.juan_num == juan_num)
    if lang is not None:
        query = query.where(TextContent.lang == lang)
    else:
        # Prefer the text's own language when no lang specified
        query = query.order_by((TextContent.lang == bt.lang).desc())
    query = query.limit(1)
    result = await session.execute(query)
    tc = result.scalars().first()
    if tc is None:
        return None

    # Get all distinct juan numbers to compute prev/next (use default lang to avoid duplicates)
    result = await session.execute(
        select(TextContent.juan_num)
        .where(TextContent.text_id == text_id, TextContent.lang == (lang or bt.lang))
        .order_by(TextContent.juan_num)
    )
    all_juans = [r[0] for r in result.all()]
    # Fallback: if no juans found with the specific lang filter, query without lang filter
    if not all_juans:
        result = await session.execute(
            select(TextContent.juan_num)
            .where(TextContent.text_id == text_id)
            .distinct()
            .order_by(TextContent.juan_num)
        )
        all_juans = [r[0] for r in result.all()]
    idx = all_juans.index(juan_num) if juan_num in all_juans else -1
    prev_juan = all_juans[idx - 1] if idx > 0 else None
    next_juan = all_juans[idx + 1] if idx < len(all_juans) - 1 else None

    return JuanContentResponse(
        text_id=text_id,
        cbeta_id=bt.cbeta_id,
        title_zh=bt.title_zh,
        juan_num=juan_num,
        total_juans=len(all_juans),
        content=tc.content,
        char_count=tc.char_count,
        lang=tc.lang,
        prev_juan=prev_juan,
        next_juan=next_juan,
    )
