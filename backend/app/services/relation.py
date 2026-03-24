from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.relation import TextRelation
from app.models.text import BuddhistText, TextContent

# KG predicates we surface as text-level relations
_KG_PREDICATES = ("cites", "commentary_on")

# Map KG predicate → unified relation_type used by the frontend
_KG_PREDICATE_MAP = {
    "cites": "cites",
    "commentary_on": "commentary",
}


async def _get_text_relations_from_table(
    session: AsyncSession, text_id: int,
) -> list[dict]:
    """Get relations from text_relations table."""
    result = await session.execute(
        select(TextRelation)
        .options(joinedload(TextRelation.text_a), joinedload(TextRelation.text_b))
        .where(or_(TextRelation.text_a_id == text_id, TextRelation.text_b_id == text_id))
    )
    relations = result.scalars().all()

    items = []
    for rel in relations:
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


async def _get_kg_text_relations(
    session: AsyncSession, text_id: int,
) -> list[dict]:
    """Get text-to-text relations from the knowledge graph.

    Uses a single UNION ALL query to find both outgoing and incoming relations.
    """
    SubjectEntity = aliased(KGEntity)
    ObjectEntity = aliased(KGEntity)

    # Outgoing: this text is the subject
    outgoing_q = (
        select(
            KGRelation.predicate,
            KGRelation.confidence,
            BuddhistText.id.label("bt_id"),
            BuddhistText.cbeta_id,
            BuddhistText.title_zh,
            BuddhistText.translator,
            BuddhistText.dynasty,
            BuddhistText.lang,
        )
        .join(SubjectEntity, KGRelation.subject_id == SubjectEntity.id)
        .join(ObjectEntity, KGRelation.object_id == ObjectEntity.id)
        .join(BuddhistText, ObjectEntity.text_id == BuddhistText.id)
        .where(
            SubjectEntity.text_id == text_id,
            SubjectEntity.entity_type == "text",
            ObjectEntity.entity_type == "text",
            ObjectEntity.text_id.is_not(None),
            KGRelation.predicate.in_(_KG_PREDICATES),
        )
    )

    # Incoming: this text is the object
    SubjectEntity2 = aliased(KGEntity)
    ObjectEntity2 = aliased(KGEntity)
    incoming_q = (
        select(
            KGRelation.predicate,
            KGRelation.confidence,
            BuddhistText.id.label("bt_id"),
            BuddhistText.cbeta_id,
            BuddhistText.title_zh,
            BuddhistText.translator,
            BuddhistText.dynasty,
            BuddhistText.lang,
        )
        .join(ObjectEntity2, KGRelation.object_id == ObjectEntity2.id)
        .join(SubjectEntity2, KGRelation.subject_id == SubjectEntity2.id)
        .join(BuddhistText, SubjectEntity2.text_id == BuddhistText.id)
        .where(
            ObjectEntity2.text_id == text_id,
            ObjectEntity2.entity_type == "text",
            SubjectEntity2.entity_type == "text",
            SubjectEntity2.text_id.is_not(None),
            KGRelation.predicate.in_(_KG_PREDICATES),
        )
    )

    combined = outgoing_q.union_all(incoming_q)
    result = await session.execute(combined)

    items: list[dict] = []
    for row in result.all():
        items.append({
            "text_id": row.bt_id,
            "cbeta_id": row.cbeta_id,
            "title_zh": row.title_zh,
            "translator": row.translator,
            "dynasty": row.dynasty,
            "lang": row.lang,
            "relation_type": _KG_PREDICATE_MAP.get(row.predicate, row.predicate),
            "confidence": row.confidence,
            "note": None,
        })
    return items


async def get_text_relations(session: AsyncSession, text_id: int) -> list[dict]:
    """Get all relations for a given text, merging text_relations and KG data."""
    table_items = await _get_text_relations_from_table(session, text_id)
    kg_items = await _get_kg_text_relations(session, text_id)

    # Deduplicate by (text_id, relation_type), preferring text_relations rows
    seen: set[tuple[int, str]] = set()
    merged: list[dict] = []
    for item in table_items:
        key = (item["text_id"], item["relation_type"])
        if key not in seen:
            seen.add(key)
            merged.append(item)
    for item in kg_items:
        key = (item["text_id"], item["relation_type"])
        if key not in seen:
            seen.add(key)
            merged.append(item)

    return merged


async def get_parallel_content(
    session: AsyncSession, text_a_id: int, text_b_id: int, juan_num: int = 1
) -> dict | None:
    """Get parallel content for two texts at a given juan."""
    text_a = await session.get(BuddhistText, text_a_id)
    text_b = await session.get(BuddhistText, text_b_id)
    if not text_a or not text_b:
        return None

    # Prefer content in the text's own language, fall back to any available
    content_a = await session.execute(
        select(TextContent)
        .where(TextContent.text_id == text_a_id, TextContent.juan_num == juan_num)
        .order_by((TextContent.lang == text_a.lang).desc())
        .limit(1)
    )
    content_b = await session.execute(
        select(TextContent)
        .where(TextContent.text_id == text_b_id, TextContent.juan_num == juan_num)
        .order_by((TextContent.lang == text_b.lang).desc())
        .limit(1)
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
