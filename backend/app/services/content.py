from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.text import BuddhistText, TextApparatus, TextContent, TextLineAnchor
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

    from app.services.text import canon_from_cbeta_id, canon_label_zh

    canon = canon_from_cbeta_id(bt.cbeta_id)
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
        canon=canon,
        canon_label=canon_label_zh(canon),
    )


async def get_juan_apparatus(session: AsyncSession, text_id: int, juan_num: int) -> list[dict]:
    """Aligned critical-apparatus (校勘异文) entries for one juan, ordered by
    position. Unaligned entries (no resolvable offset) are excluded — the reader
    renders by char offset, so only aligned rows are returned."""
    result = await session.execute(
        select(TextApparatus)
        .where(
            TextApparatus.text_id == text_id,
            TextApparatus.juan_num == juan_num,
            TextApparatus.aligned.is_(True),
        )
        .options(selectinload(TextApparatus.readings))
        .order_by(TextApparatus.char_start)
    )
    return [
        {
            "char_start": e.char_start,
            "char_end": e.char_end,
            "lemma": e.lemma,
            "lemma_siglum": e.lemma_siglum,
            "readings": [
                {
                    "reading": r.reading,
                    "witnesses": list(r.witnesses or []),
                    "resp": r.resp,
                    "is_omission": r.is_omission,
                }
                for r in e.readings
            ],
        }
        for e in result.scalars().all()
    ]


async def get_juan_line_anchors(session: AsyncSession, text_id: int, juan_num: int) -> list[dict]:
    """CBETA <lb> page-column-line anchors for one juan, ordered by position.
    Each: {char_offset, line_ref} (line_ref e.g. "0001a09"). Drives the reader's
    on-demand citation locator and URN #anchor scroll-to-line."""
    result = await session.execute(
        select(TextLineAnchor.char_offset, TextLineAnchor.line_ref)
        .where(TextLineAnchor.text_id == text_id, TextLineAnchor.juan_num == juan_num)
        .order_by(TextLineAnchor.char_offset)
    )
    return [{"char_offset": off, "line_ref": ref} for off, ref in result.all()]
