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

    # Exclude manually hidden entities (properties.is_hidden=true)
    stmt = stmt.where(
        func.coalesce(
            KGEntity.properties.op("->>")("is_hidden"), "false"
        )
        != "true"
    )

    # Exclude entities without any KG relations — they add no value to the graph
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
    ent = await session.get(KGEntity, entity_id)
    if ent is None:
        return None
    props = ent.properties or {}
    if str(props.get("is_hidden", "false")).lower() == "true":
        return None
    return ent


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
        """)  # nosec B608 - pred_filter is a hardcoded clause, not user input
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
    """)  # nosec B608 - pred_filter is a hardcoded clause, not user input
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
            select(KGEntity).where(
                KGEntity.id.in_(node_ids),
                func.coalesce(
                    KGEntity.properties["is_hidden"].astext, "false"
                )
                != "true",
            )
        )
        for e in entities_result.scalars().all():
            nodes.append({
                "id": e.id,
                "name": e.name_zh,
                "entity_type": e.entity_type,
                "description": e.description,
            })
        visible_ids = {n["id"] for n in nodes}
        links = [
            link for link in links
            if link["source"] in visible_ids and link["target"] in visible_ids
        ]

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


async def get_geo_entities(
    session: AsyncSession,
    entity_types: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    bounds: tuple[float, float, float, float] | None = None,
    limit: int = 5000,
) -> tuple[list[dict], int]:
    """Get entities with geographic coordinates, with optional filtering.

    获取具有地理坐标的实体，支持类型/时间/边界框过滤。"""
    conditions = [
        "(e.properties->>'latitude') IS NOT NULL",
        "(e.properties->>'longitude') IS NOT NULL",
        "e.entity_type != 'sub_entity'",
        "COALESCE(e.properties->>'is_buddhist', 'true') != 'false'",
        "COALESCE(e.properties->>'is_hidden', 'false') != 'true'",
        # person 只放高置信度 + 中国境内；teacher_hop / desc_match 有误匹配（中国僧人投海外同名寺）
        # monastery / place 等不受影响
        """(
            e.entity_type != 'person'
            OR (
                (e.properties->>'latitude')::float BETWEEN 18 AND 54
                AND (e.properties->>'longitude')::float BETWEEN 73 AND 135
                AND (
                    e.properties->>'geo_source' LIKE 'wikidata%'
                    OR e.properties->>'geo_source' LIKE 'city_match%'
                    OR e.properties->>'geo_source' LIKE 'province_match%'
                )
            )
        )""",
    ]
    params: dict = {"limit": limit}

    if entity_types:
        conditions.append("e.entity_type = ANY(:entity_types)")
        params["entity_types"] = entity_types

    if year_start is not None:
        conditions.append(
            "COALESCE((e.properties->>'year_end')::int, 9999) >= :year_start"
        )
        params["year_start"] = year_start

    if year_end is not None:
        conditions.append(
            "COALESCE((e.properties->>'year_start')::int, -9999) <= :year_end"
        )
        params["year_end"] = year_end

    if bounds:
        south, west, north, east = bounds
        conditions.append(
            "(e.properties->>'latitude')::float BETWEEN :south AND :north"
        )
        conditions.append(
            "(e.properties->>'longitude')::float BETWEEN :west AND :east"
        )
        params.update(south=south, west=west, north=north, east=east)

    where_clause = " AND ".join(conditions)

    count_sql = text(
        f"SELECT COUNT(*) FROM kg_entities e WHERE {where_clause}"  # nosec B608
    )
    count_result = await session.execute(count_sql, params)
    total = count_result.scalar() or 0

    sql = text(
        f"""
        SELECT
            e.id,
            e.entity_type,
            e.name_zh,
            e.name_en,
            e.description,
            (e.properties->>'latitude')::float AS latitude,
            (e.properties->>'longitude')::float AS longitude,
            (e.properties->>'year_start')::int AS year_start,
            (e.properties->>'year_end')::int AS year_end,
            e.properties->>'province' AS province,
            e.properties->>'city' AS city,
            e.properties->>'district' AS district
        FROM kg_entities e
        WHERE {where_clause}
        ORDER BY e.id
        LIMIT :limit
        """  # nosec B608
    )
    result = await session.execute(sql, params)
    entities = [
        {
            "id": row[0],
            "entity_type": row[1],
            "name_zh": row[2],
            "name_en": row[3],
            "description": row[4],
            "latitude": row[5],
            "longitude": row[6],
            "year_start": row[7],
            "year_end": row[8],
            "province": row[9],
            "city": row[10],
            "district": row[11],
        }
        for row in result.fetchall()
    ]
    return entities, total


async def get_lineage_arcs(
    session: AsyncSession,
    school: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    limit: int = 5000,
) -> tuple[list[dict], int]:
    """Get teacher-student lineage arcs with geographic coordinates.

    获取具有地理坐标的师承传法弧线。"""
    conditions = [
        "r.predicate = 'teacher_of'",
        "(t.properties->>'latitude') IS NOT NULL",
        "(t.properties->>'longitude') IS NOT NULL",
        "(s.properties->>'latitude') IS NOT NULL",
        "(s.properties->>'longitude') IS NOT NULL",
        "(t.properties->>'latitude') != ''",
        "(s.properties->>'latitude') != ''",
        "COALESCE(t.properties->>'geo_source', '') NOT LIKE 'teacher_hop%%'",
        "COALESCE(s.properties->>'geo_source', '') NOT LIKE 'teacher_hop%%'",
        "COALESCE(t.properties->>'is_buddhist', 'true') != 'false'",
        "COALESCE(s.properties->>'is_buddhist', 'true') != 'false'",
        "COALESCE(t.properties->>'is_hidden', 'false') != 'true'",
        "COALESCE(s.properties->>'is_hidden', 'false') != 'true'",
        # 与 person 图层同款白名单：中国 bbox + 高置信度坐标
        # desc_match 贪心匹配会把中国僧人投到同名韩国/日本寺院，端点坐标不可信
        "(t.properties->>'latitude')::float BETWEEN 18 AND 54",
        "(t.properties->>'longitude')::float BETWEEN 73 AND 135",
        "(s.properties->>'latitude')::float BETWEEN 18 AND 54",
        "(s.properties->>'longitude')::float BETWEEN 73 AND 135",
        """(
            t.properties->>'geo_source' LIKE 'wikidata%'
            OR t.properties->>'geo_source' LIKE 'city_match%'
            OR t.properties->>'geo_source' LIKE 'province_match%'
        )""",
        """(
            s.properties->>'geo_source' LIKE 'wikidata%'
            OR s.properties->>'geo_source' LIKE 'city_match%'
            OR s.properties->>'geo_source' LIKE 'province_match%'
        )""",
    ]
    params: dict = {"limit": limit}

    if school:
        conditions.append("""
            EXISTS (
                SELECT 1 FROM kg_relations r2
                WHERE r2.predicate = 'member_of_school'
                AND r2.subject_id = s.id
                AND r2.object_id IN (
                    SELECT id FROM kg_entities WHERE name_zh = :school
                )
            )
        """)
        params["school"] = school

    if year_start is not None:
        conditions.append(
            "COALESCE((s.properties->>'year_start')::int,"
            " (t.properties->>'year_end')::int, 9999) >= :year_start"
        )
        params["year_start"] = year_start

    if year_end is not None:
        conditions.append(
            "COALESCE((s.properties->>'year_start')::int,"
            " (t.properties->>'year_end')::int, -9999) <= :year_end"
        )
        params["year_end"] = year_end

    where_clause = " AND ".join(conditions)

    count_sql = text(
        f"""
        SELECT COUNT(*) FROM kg_relations r
        JOIN kg_entities t ON t.id = r.subject_id
        JOIN kg_entities s ON s.id = r.object_id
        WHERE {where_clause}
        """  # nosec B608
    )
    count_result = await session.execute(count_sql, params)
    total = count_result.scalar() or 0

    sql = text(
        f"""
        SELECT
            t.id AS teacher_id,
            t.name_zh AS teacher_name,
            (t.properties->>'latitude')::float AS teacher_lat,
            (t.properties->>'longitude')::float AS teacher_lng,
            s.id AS student_id,
            s.name_zh AS student_name,
            (s.properties->>'latitude')::float AS student_lat,
            (s.properties->>'longitude')::float AS student_lng,
            COALESCE(
                (s.properties->>'year_start')::int,
                (t.properties->>'year_end')::int
            ) AS year,
            (
                SELECT e2.name_zh FROM kg_relations r2
                JOIN kg_entities e2 ON e2.id = r2.object_id
                WHERE r2.predicate = 'member_of_school'
                AND r2.subject_id = s.id
                LIMIT 1
            ) AS school
        FROM kg_relations r
        JOIN kg_entities t ON t.id = r.subject_id
        JOIN kg_entities s ON s.id = r.object_id
        WHERE {where_clause}
        ORDER BY year NULLS LAST
        LIMIT :limit
        """  # nosec B608
    )
    result = await session.execute(sql, params)
    arcs = [
        {
            "teacher_id": row[0],
            "teacher_name": row[1],
            "teacher_lat": row[2],
            "teacher_lng": row[3],
            "student_id": row[4],
            "student_name": row[5],
            "student_lat": row[6],
            "student_lng": row[7],
            "year": row[8],
            "school": row[9],
        }
        for row in result.fetchall()
    ]
    return arcs, total
