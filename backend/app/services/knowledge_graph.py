from opencc import OpenCC
from sqlalchemy import case, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_graph import KGEntity, KGRelation

_s2t = OpenCC("s2t")
_t2s = OpenCC("t2s")

# ── Graph traversal hard limits ──
MAX_NODES_DEFAULT = 150
MAX_EDGES_DEFAULT = 500


def _zh_variants(q: str) -> list[str]:
    """Return deduplicated [original, simplified, traditional] variants."""
    variants = {q, _t2s.convert(q), _s2t.convert(q)}
    return list(variants)


async def search_entities(
    session: AsyncSession,
    q: str,
    entity_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    has_relations: bool | None = None,
) -> tuple[list[KGEntity], int]:
    variants = _zh_variants(q)
    # Build OR conditions: each variant against zh, each original q against sa/pi/bo/en
    zh_conditions = [KGEntity.name_zh.ilike(f"%{v}%") for v in variants]
    stmt = select(KGEntity).where(
        or_(
            *zh_conditions,
            KGEntity.name_sa.ilike(f"%{q}%"),
            KGEntity.name_pi.ilike(f"%{q}%"),
            KGEntity.name_bo.ilike(f"%{q}%"),
            KGEntity.name_en.ilike(f"%{q}%"),
        )
    )

    if entity_type:
        stmt = stmt.where(KGEntity.entity_type == entity_type)

    if has_relations is True:
        stmt = stmt.where(
            exists(
                select(KGRelation.id).where(
                    or_(
                        KGRelation.subject_id == KGEntity.id,
                        KGRelation.object_id == KGEntity.id,
                    )
                )
            )
        )

    count_stmt = select(func.count()).select_from(
        stmt.with_only_columns(KGEntity.id).subquery()
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Relevance sorting: exact > prefix > contains; person/school before text
    # Use first variant (original query) for matching
    relevance = case(
        (KGEntity.name_zh == q, 0),
        (KGEntity.name_zh.startswith(q), 1),
        else_=2,
    )
    type_priority = case(
        (KGEntity.entity_type == "person", 0),
        (KGEntity.entity_type == "school", 1),
        (KGEntity.entity_type == "dynasty", 2),
        else_=3,
    )
    stmt = stmt.order_by(relevance, type_priority, KGEntity.id).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def get_entity(session: AsyncSession, entity_id: int) -> KGEntity | None:
    return await session.get(KGEntity, entity_id)


async def get_entity_relations(
    session: AsyncSession, entity_id: int
) -> list[dict]:
    """Get all relations for an entity with resolved target names."""
    sql = text("""
        SELECT
            r.predicate,
            CASE WHEN r.subject_id = :eid THEN 'outgoing' ELSE 'incoming' END AS direction,
            CASE WHEN r.subject_id = :eid THEN r.object_id ELSE r.subject_id END AS target_id,
            e.name_zh AS target_name,
            e.entity_type AS target_type,
            r.confidence,
            r.source
        FROM kg_relations r
        JOIN kg_entities e ON e.id = CASE WHEN r.subject_id = :eid THEN r.object_id ELSE r.subject_id END
        WHERE r.subject_id = :eid OR r.object_id = :eid
        ORDER BY r.predicate, e.name_zh
    """)
    result = await session.execute(sql, {"eid": entity_id})
    return [
        {
            "predicate": row[0],
            "direction": row[1],
            "target_id": row[2],
            "target_name": row[3],
            "target_type": row[4],
            "confidence": row[5],
            "source": row[6],
        }
        for row in result.fetchall()
    ]


async def get_entity_graph(
    session: AsyncSession,
    entity_id: int,
    depth: int = 2,
    max_nodes: int = MAX_NODES_DEFAULT,
    predicates: list[str] | None = None,
) -> dict:
    """Get graph around an entity using layered BFS with hard limits.

    Returns at most *max_nodes* nodes and MAX_EDGES_DEFAULT edges.
    Cross-source duplicate edges are collapsed (keep highest confidence).
    """
    # ── Layered BFS in Python (avoids CTE explosion) ──
    visited: set[int] = {entity_id}
    frontier: set[int] = {entity_id}
    truncated = False

    # Build optional predicate filter clause
    pred_filter = ""
    params: dict = {"max_nodes": max_nodes}
    if predicates:
        pred_filter = "AND r.predicate = ANY(:predicates)"
        params["predicates"] = predicates

    for _layer in range(depth):
        if not frontier:
            break

        # Fetch neighbors of frontier nodes
        sql = text(f"""
            SELECT DISTINCT
                CASE WHEN r.subject_id = ANY(:frontier) THEN r.object_id ELSE r.subject_id END AS neighbor
            FROM kg_relations r
            WHERE (r.subject_id = ANY(:frontier) OR r.object_id = ANY(:frontier))
            {pred_filter}
        """)
        result = await session.execute(sql, {**params, "frontier": list(frontier)})
        neighbors = {row[0] for row in result.fetchall()}

        new_nodes = neighbors - visited
        # Enforce node cap
        room = max_nodes - len(visited)
        if room <= 0:
            truncated = True
            break
        if len(new_nodes) > room:
            new_nodes = set(list(new_nodes)[:room])
            truncated = True

        visited.update(new_nodes)
        frontier = new_nodes

    # ── Fetch edges within the discovered subgraph (deduplicated) ──
    node_ids = list(visited)
    if not node_ids:
        return {"nodes": [], "links": [], "truncated": False}

    edge_sql = text(f"""
        SELECT subject_id, predicate, object_id,
               MAX(confidence) AS confidence,
               (array_agg(source ORDER BY confidence DESC))[1] AS source,
               (array_agg(properties ORDER BY confidence DESC))[1] AS properties
        FROM kg_relations r
        WHERE r.subject_id = ANY(:ids) AND r.object_id = ANY(:ids)
        {pred_filter}
        GROUP BY subject_id, predicate, object_id
    """)
    edge_result = await session.execute(edge_sql, {**params, "ids": node_ids})
    edge_rows = edge_result.fetchall()

    links = []
    for row in edge_rows:
        if len(links) >= MAX_EDGES_DEFAULT:
            truncated = True
            break
        # Extract evidence summary from properties
        props = row[5] if row[5] else {}
        evidence_parts = []
        if props.get("evidence_note"):
            evidence_parts.append(props["evidence_note"][:80])
        if props.get("evidence_rule"):
            evidence_parts.append(props["evidence_rule"])
        if props.get("evidence_source_title"):
            evidence_parts.append(props["evidence_source_title"])

        links.append({
            "source": row[0],
            "target": row[2],
            "predicate": row[1],
            "confidence": row[3],
            "provenance": row[4],
            "evidence": "; ".join(evidence_parts) if evidence_parts else None,
        })

    # ── Fetch entity details ──
    nodes = []
    if node_ids:
        entities_result = await session.execute(
            select(KGEntity).where(KGEntity.id.in_(node_ids))
        )
        for e in entities_result.scalars().all():
            nodes.append({
                "id": e.id,
                "name": e.name_zh,
                "entity_type": e.entity_type,
                "description": e.description,
            })

    return {"nodes": nodes, "links": links, "truncated": truncated}


async def get_kg_stats(session: AsyncSession) -> dict:
    """Return aggregate KG statistics: entity/relation counts by type."""
    entity_sql = text(
        "SELECT entity_type, COUNT(*) FROM kg_entities GROUP BY entity_type ORDER BY COUNT(*) DESC"
    )
    relation_sql = text(
        "SELECT predicate, COUNT(*) FROM kg_relations GROUP BY predicate ORDER BY COUNT(*) DESC"
    )
    entity_result = await session.execute(entity_sql)
    relation_result = await session.execute(relation_sql)

    entity_counts = {row[0]: row[1] for row in entity_result.fetchall()}
    relation_counts = {row[0]: row[1] for row in relation_result.fetchall()}

    return {
        "entities": entity_counts,
        "relations": relation_counts,
        "total_entities": sum(entity_counts.values()),
        "total_relations": sum(relation_counts.values()),
    }


async def get_text_entities(session: AsyncSession, text_id: int) -> list[KGEntity]:
    """Get all KG entities linked to a specific text."""
    result = await session.execute(
        select(KGEntity).where(KGEntity.text_id == text_id)
    )
    return list(result.scalars().all())
