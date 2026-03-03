from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.relation import TextRelation
from app.models.text import BuddhistText, TextContent


async def get_text_relations(session: AsyncSession, text_id: int) -> list[dict]:
    """Get all relations for a given text (as either side)."""
    result = await session.execute(
        select(TextRelation)
        .options(joinedload(TextRelation.text_a), joinedload(TextRelation.text_b))
        .where(or_(TextRelation.text_a_id == text_id, TextRelation.text_b_id == text_id))
    )
    relations = result.scalars().all()

    items = []
    for rel in relations:
        # Return the "other" text in the relation
        if rel.text_a_id == text_id:
            other = rel.text_b
        else:
            other = rel.text_a

        items.append({
            "text_id": other.id,
            "cbeta_id": other.cbeta_id,
            "title_zh": other.title_zh,
            "translator": other.translator,
            "dynasty": other.dynasty,
            "lang": other.lang,
            "relation_type": rel.relation_type,
            "confidence": rel.confidence,
            "note": rel.note,
        })
    return items


async def get_parallel_content(
    session: AsyncSession, text_a_id: int, text_b_id: int, juan_num: int = 1
) -> dict | None:
    """Get parallel content for two texts at a given juan."""
    text_a = await session.get(BuddhistText, text_a_id)
    text_b = await session.get(BuddhistText, text_b_id)
    if not text_a or not text_b:
        return None

    content_a = await session.execute(
        select(TextContent).where(
            TextContent.text_id == text_a_id, TextContent.juan_num == juan_num
        )
    )
    content_b = await session.execute(
        select(TextContent).where(
            TextContent.text_id == text_b_id, TextContent.juan_num == juan_num
        )
    )
    ca = content_a.scalar_one_or_none()
    cb = content_b.scalar_one_or_none()

    return {
        "text_a": {
            "text_id": text_a.id,
            "cbeta_id": text_a.cbeta_id,
            "title_zh": text_a.title_zh,
            "translator": text_a.translator,
            "lang": text_a.lang,
            "juan_num": juan_num,
            "content": ca.content if ca else "",
        },
        "text_b": {
            "text_id": text_b.id,
            "cbeta_id": text_b.cbeta_id,
            "title_zh": text_b.title_zh,
            "translator": text_b.translator,
            "lang": text_b.lang,
            "juan_num": juan_num,
            "content": cb.content if cb else "",
        },
    }
