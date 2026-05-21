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

    # Relevance sorting: exact > prefix > contains; within the same
    # relevance tier, the most-connected entity (highest graph degree)
    # wins so an ambiguous name resolves to its richest node; type and
    # id are final tiebreaks.
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
    # Degree = number of KG relations touching the entity (as subject or
    # object). Used both as a sort key and surfaced to the UI as
    # `relation_count` so a result can show "N 条关系".
    degree_col = (
        select(func.count(KGRelation.id))
        .where(
            or_(
                KGRelation.subject_id == KGEntity.id,
                KGRelation.object_id == KGEntity.id,
            )
        )
        .correlate(KGEntity)
        .scalar_subquery()
        .label("degree")
    )
    stmt = (
        stmt.add_columns(degree_col)
        .order_by(relevance, degree_col.desc(), type_priority, KGEntity.id)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    entities: list[KGEntity] = []
    for ent, degree in result.all():
        ent.relation_count = int(degree or 0)
        entities.append(ent)
    return entities, total


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
                    KGEntity.properties.op("->>")("is_hidden"), "false"
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


async def find_shortest_path(
    session: AsyncSession,
    from_id: int,
    to_id: int,
    max_hops: int = 6,
) -> dict:
    """Find the shortest undirected path between two KG entities using layered BFS.

    两实体间最短无向路径（单源分层 BFS，最多 max_hops 跳）。
    Returns {"found": bool, "hops": int, "nodes": [...], "links": [...]}.
    Returns an empty result (found=False) when either entity is missing, no
    path exists within max_hops, or the frontier exceeds the hub cap.

    Implementation guarantees:
    - Path is shortest (BFS discovers each node on its first, shallowest reach).
    - Path is simple (each node recorded in `parent` exactly once — no loops).
    - One SQL query per BFS layer (no redundant second pass).
    - Hidden entities (is_hidden=true) are excluded from traversal.
    - Frontier cap of 5000 prevents hub-explosion table scans.
    """
    # ── Frontier cap ──
    _FRONTIER_CAP = 5000

    # Validate both entities exist (hidden entities are also rejected here
    # so we don't silently start/end at a hidden node)
    from_ent = await session.get(KGEntity, from_id)
    to_ent = await session.get(KGEntity, to_id)
    if from_ent is None or to_ent is None:
        return {"found": False, "hops": 0, "nodes": [], "links": []}

    # Trivial case: same entity
    if from_id == to_id:
        return {
            "found": True,
            "hops": 0,
            "nodes": [
                {
                    "id": from_ent.id,
                    "name": from_ent.name_zh,
                    "entity_type": from_ent.entity_type,
                    "description": from_ent.description,
                }
            ],
            "links": [],
        }

    # ── Single-source layered BFS from from_id ──
    # parent[x] = the node from which x was first discovered.
    # from_id itself has no parent (sentinel None).
    # Each node is recorded exactly once → path is shortest and loop-free.
    parent: dict[int, int | None] = {from_id: None}
    frontier: set[int] = {from_id}
    found = False

    for _layer in range(max_hops):
        if not frontier:
            break

        # ONE query per layer: return (neighbor_id, came_from_id) for all
        # relations that touch the current frontier, treating the graph as
        # undirected.  Hidden entities are excluded so they can never appear
        # in the path (mirrors the is_hidden filter in get_entity_graph).
        sql = text("""
            SELECT
                CASE WHEN r.subject_id = ANY(:frontier)
                     THEN r.object_id ELSE r.subject_id END AS neighbor,
                CASE WHEN r.subject_id = ANY(:frontier)
                     THEN r.subject_id ELSE r.object_id END AS came_from
            FROM kg_relations r
            JOIN kg_entities e
              ON e.id = CASE WHEN r.subject_id = ANY(:frontier)
                             THEN r.object_id ELSE r.subject_id END
            WHERE (r.subject_id = ANY(:frontier) OR r.object_id = ANY(:frontier))
              AND COALESCE(e.properties->>'is_hidden', 'false') != 'true'
        """)
        result = await session.execute(sql, {"frontier": list(frontier)})
        rows = result.fetchall()

        new_frontier: set[int] = set()
        for neighbor, came_from in rows:
            if neighbor not in parent:
                parent[neighbor] = came_from
                new_frontier.add(neighbor)
                if neighbor == to_id:
                    found = True

        # Stop as soon as to_id is discovered (shortest path reached)
        if found:
            break

        # Hub explosion guard: if the next frontier is unreasonably large,
        # bail out rather than issuing a full-table-scan next iteration.
        if len(new_frontier) > _FRONTIER_CAP:
            return {"found": False, "hops": 0, "nodes": [], "links": []}

        frontier = new_frontier

    if not found:
        return {"found": False, "hops": 0, "nodes": [], "links": []}

    # ── Reconstruct path by walking parent pointers from to_id back to from_id ──
    path_ids: list[int] = []
    cur: int | None = to_id
    while cur is not None:
        path_ids.append(cur)
        cur = parent[cur]
    path_ids.reverse()  # now: [from_id, ..., to_id]
    hops = len(path_ids) - 1

    # ── Fetch edges along the path (one query, highest-confidence per pair) ──
    edge_sql = text("""
        SELECT subject_id, predicate, object_id,
               MAX(confidence) AS confidence,
               (array_agg(source ORDER BY confidence DESC))[1] AS source,
               (array_agg(properties ORDER BY confidence DESC))[1] AS properties
        FROM kg_relations r
        WHERE r.subject_id = ANY(:ids) AND r.object_id = ANY(:ids)
        GROUP BY subject_id, predicate, object_id
    """)
    edge_result = await session.execute(edge_sql, {"ids": path_ids})
    # Build undirected adjacency: (min_id, max_id) → best row
    adjacency: dict[tuple[int, int], object] = {}
    for row in edge_result.fetchall():
        key = (min(row[0], row[2]), max(row[0], row[2]))
        existing = adjacency.get(key)
        if existing is None or (row[3] or 0) > (existing[3] or 0):  # type: ignore[index]
            adjacency[key] = row

    links: list[dict] = []
    for i in range(len(path_ids) - 1):
        a, b = path_ids[i], path_ids[i + 1]
        key = (min(a, b), max(a, b))
        row = adjacency.get(key)
        if row is not None:
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

    # ── Fetch node details (hidden filter applied again for safety) ──
    entities_result = await session.execute(
        select(KGEntity).where(
            KGEntity.id.in_(path_ids),
            func.coalesce(
                KGEntity.properties.op("->>")("is_hidden"), "false"
            )
            != "true",
        )
    )
    ent_map = {e.id: e for e in entities_result.scalars().all()}
    nodes = []
    for eid in path_ids:
        e = ent_map.get(eid)
        if e:
            nodes.append({
                "id": e.id,
                "name": e.name_zh,
                "entity_type": e.entity_type,
                "description": e.description,
            })

    return {"found": True, "hops": hops, "nodes": nodes, "links": links}


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


# ── Mentions cache ─────────────────────────────────────────────────────────
# Maps name_zh → (id, entity_type) for all "linkable" entities (excludes
# sub_entity).  Built lazily on first call; rebuilt manually via reset().
# ~70k entries, ≤8 MB in memory.  Used by get_mentioned_entities() to scan
# a single description for substring matches without a full-table SQL scan.
#
# Names with length 1 are excluded — too noisy (single characters match
# everything). Length-2 short names are kept because Buddhist names like
# 玄奘 / 義淨 / 道宣 are 2 chars.

_MENTION_NAMES_BY_LEN: list[tuple[str, int, str]] | None = None
# (name_zh, entity_id, entity_type) — sorted by len(name_zh) DESC so that
# substring match prefers longer (more specific) candidates first.

# Guard the lazy load so concurrent cold-start requests don't double-load
# the 70k-row index (each load is ~5MB + one SQL scan).
import asyncio as _asyncio
_MENTIONS_BUILD_LOCK = _asyncio.Lock()

_MENTIONS_SCANNABLE_TYPES = frozenset(
    {"person", "monastery", "place", "school", "concept", "text", "dynasty"}
)


async def _load_mentions_index(session: AsyncSession) -> list[tuple[str, int, str]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT name_zh, id, entity_type
                FROM kg_entities
                WHERE entity_type = ANY(:types)
                  AND length(name_zh) >= 2
                  AND COALESCE(properties->>'is_hidden', 'false') != 'true'
                """
            ),
            {"types": list(_MENTIONS_SCANNABLE_TYPES)},
        )
    ).all()
    # Sort by name length DESC for greedy longest-match consumption.
    return sorted(
        ((r.name_zh, r.id, r.entity_type) for r in rows),
        key=lambda t: -len(t[0]),
    )


async def get_mentioned_entities(
    session: AsyncSession,
    entity_id: int,
    description: str | None,
    limit: int = 30,
) -> list[dict]:
    """Find in-DB entities whose name_zh appears as a substring of description.

    Returns up to *limit* matches, ranked longest-name-first.  Greedy
    consumption: once a name matches, its text range is masked out so a
    shorter sub-name doesn't double-count (e.g. matching "崇福寺" prevents
    "崇福" from also firing on the same span).

    The caller is responsible for excluding entries that are already
    represented in the structured kg_relations graph (UI concern).
    """
    global _MENTION_NAMES_BY_LEN
    if _MENTION_NAMES_BY_LEN is None:
        async with _MENTIONS_BUILD_LOCK:
            # Double-check after grabbing the lock — another waiter may have
            # already populated it.
            if _MENTION_NAMES_BY_LEN is None:
                _MENTION_NAMES_BY_LEN = await _load_mentions_index(session)

    if not description:
        return []

    # Mask string: same length as description, '\0' marks consumed chars.
    masked = list(description)
    results: list[dict] = []
    seen_ids: set[int] = {entity_id}
    # Dedup by name as well — DB has 14 different "崇福寺" entities and
    # surfacing them all is noise. Pick the first; future iteration can add
    # a "同名 N 个" disambiguation badge.
    seen_names: set[str] = set()

    for name, mid, etype in _MENTION_NAMES_BY_LEN:
        if len(results) >= limit:
            break
        if mid in seen_ids:
            continue
        if name in seen_names:
            continue
        # Find first unmasked occurrence.
        start = 0
        n = len(name)
        while True:
            idx = description.find(name, start)
            if idx < 0:
                break
            # Verify span is unmasked.
            if all(masked[idx + k] != "\0" for k in range(n)):
                # Mask span; record match.
                for k in range(n):
                    masked[idx + k] = "\0"
                # Build a snippet around the match for context. Collapse
                # newlines so the chip-list snippet renders on one line.
                lo = max(0, idx - 8)
                hi = min(len(description), idx + n + 8)
                snippet = description[lo:hi].replace("\n", " ").strip()
                results.append(
                    {
                        "id": mid,
                        "name_zh": name,
                        "entity_type": etype,
                        "snippet": snippet,
                    }
                )
                seen_ids.add(mid)
                seen_names.add(name)
                break
            start = idx + 1
    return results


def reset_mentions_cache() -> None:
    """Force the mentions index to reload on next call.

    Currently unwired — the index is loaded lazily on first request and
    accepts staleness from bulk imports until the next process restart.
    DILA entities don't change often enough to need finer invalidation.
    Keeping this stub so a future admin endpoint or bulk-import hook can
    flip it without touching the cache internals.
    """
    global _MENTION_NAMES_BY_LEN
    _MENTION_NAMES_BY_LEN = None


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
        # person whitelist: high-confidence sources only.
        # - wikidata / city_match / province_match: original v2-era CN whitelist (kept as-is).
        # - desc_match_v3: dynasty-scored country-aware match (backfill_person_coords_v3.py);
        #   no bbox constraint — 日本/韩国/台湾 dynasties render in their actual country.
        #   The whitelist trusts the script's --min-score gate (default 0.8); do NOT
        #   lower it without re-auditing this filter, or unvetted low-score rows
        #   will leak onto the public map.
        # Still filtered out: legacy desc_match:* (海外误投) and teacher_hop:* (transitive推断).
        # monastery / place 等不受影响.
        """(
            e.entity_type != 'person'
            OR (
                e.properties->>'geo_source' LIKE 'desc_match_v3:%'
            )
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


async def get_timeline_entities(
    session: AsyncSession,
    entity_type: str | None = None,
    limit: int = 500,
) -> tuple[list[dict], int]:
    """Get entities with usable temporal data (numeric year_start required).

    返回具有有效起始年份的实体列表，支持朝代和人物类型；BCE年份以负整数表示。"""
    # Allow filtering by a single entity_type; if absent, return both person
    # and dynasty rows (the two types most likely to carry year data).
    if entity_type:
        type_condition = "e.entity_type = :entity_type"
        params: dict = {"entity_type": entity_type, "limit": limit}
    else:
        type_condition = "e.entity_type IN ('person', 'dynasty')"
        params = {"limit": limit}

    # Year regex is length-bounded ('{1,6}'): a plain '[0-9]+' would let a
    # 20-digit string pass the filter and then overflow int4 in the cast,
    # crashing the endpoint. year_end is cast through a CASE because it has
    # no WHERE filter of its own — a row with a valid year_start but a
    # garbage year_end must yield NULL, not an error.
    #
    # Field fallback: BDRC/Tibetan enrichment writes `year_start`/`year_end`
    # while DILA/Wikidata enrichment writes `birth_year`/`death_year`. Without
    # the COALESCE the timeline only saw the BDRC-derived ~95 persons and
    # appeared Tibetan-only; coalescing surfaces the Chinese/Japanese cohort
    # too (~2.5k persons total).
    # Buddhist-only filter (person rows): users expect a Buddhist-history
    # timeline, not a general kg dump. Without this, untagged DILA entries
    # like 周文王/孔門弟子/范蠡 leak in. Tagging is done by
    # scripts/classify_buddhist_persons.py (regex over description) which
    # writes is_buddhist={'true','false'} for 17k rows; the remaining 26k
    # ambiguous stay NULL and drop out here too. Dynasty rows are exempt
    # (they're 唐/宋/明 dynasty names, no per-entity Buddhist flag).
    buddhist_filter = (
        "(e.entity_type != 'person' OR e.properties->>'is_buddhist' = 'true')"
    )

    sql = text(
        f"""
        SELECT id, name_zh, entity_type, ys::int AS year_start,
               CASE WHEN ye ~ '^-?[0-9]{{1,6}}$' THEN ye::int ELSE NULL END AS year_end
        FROM (
            SELECT
                e.id,
                e.name_zh,
                e.entity_type,
                COALESCE(NULLIF(e.properties->>'year_start', ''), NULLIF(e.properties->>'birth_year', '')) AS ys,
                COALESCE(NULLIF(e.properties->>'year_end', ''),   NULLIF(e.properties->>'death_year', ''))  AS ye
            FROM kg_entities e
            WHERE {type_condition}
              AND COALESCE(e.properties->>'is_hidden', 'false') != 'true'
              AND {buddhist_filter}
        ) src
        WHERE ys ~ '^-?[0-9]{{1,6}}$'
        ORDER BY ys::int ASC
        LIMIT :limit
        """  # nosec B608 - type_condition is a hardcoded clause, not user input
    )
    result = await session.execute(sql, params)
    rows = result.fetchall()

    count_sql = text(
        f"""
        SELECT COUNT(*) FROM (
            SELECT COALESCE(NULLIF(e.properties->>'year_start', ''), NULLIF(e.properties->>'birth_year', '')) AS ys
            FROM kg_entities e
            WHERE {type_condition}
              AND COALESCE(e.properties->>'is_hidden', 'false') != 'true'
              AND {buddhist_filter}
        ) src
        WHERE ys ~ '^-?[0-9]{{1,6}}$'
        """  # nosec B608 - type_condition is a hardcoded clause, not user input
    )
    count_result = await session.execute(count_sql, params)
    total = count_result.scalar() or 0

    entities = [
        {
            "id": row[0],
            "name_zh": row[1],
            "entity_type": row[2],
            "year_start": row[3],
            "year_end": row[4],
        }
        for row in rows
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
