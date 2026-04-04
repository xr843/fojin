from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import KGEntityNotFoundError
from app.database import get_db
from app.schemas.knowledge_graph import (
    KGEntityDetailResponse,
    KGEntityResponse,
    KGGeoEntity,
    KGGeoResponse,
    KGGraphResponse,
    KGLineageArcsResponse,
    KGSearchResponse,
)
from app.services.knowledge_graph import (
    get_entity,
    get_entity_graph,
    get_entity_relations,
    get_geo_entities,
    get_kg_stats,
    get_lineage_arcs,
    get_text_entities,
    search_entities,
)

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


@router.get("/entities", response_model=KGSearchResponse)
async def search_kg_entities(
    q: str = Query(..., min_length=1),
    entity_type: str | None = None,
    has_relations: bool | None = None,
    limit: int = Query(20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Search knowledge graph entities (people, texts, schools, concepts) by name.

    搜索知识图谱实体（人物、经典、宗派、概念）。"""
    entities, total = await search_entities(
        db, q, entity_type, limit, offset, has_relations=has_relations
    )
    return KGSearchResponse(
        total=total,
        results=[KGEntityResponse.model_validate(e) for e in entities],
    )


@router.get("/entities/{entity_id}", response_model=KGEntityDetailResponse)
async def get_kg_entity(entity_id: int, db: AsyncSession = Depends(get_db)):
    """Get entity details with all its relations.

    获取实体详情及其所有关系。"""
    entity = await get_entity(db, entity_id)
    if not entity:
        raise KGEntityNotFoundError(entity_id=entity_id)
    relations = await get_entity_relations(db, entity_id)
    return KGEntityDetailResponse(
        **KGEntityResponse.model_validate(entity).model_dump(),
        relations=relations,
    )


@router.get("/entities/{entity_id}/graph", response_model=KGGraphResponse)
async def get_kg_entity_graph(
    entity_id: int,
    depth: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(150, ge=10, le=500),
    predicates: str | None = Query(None, description="Comma-separated predicate filter"),
    db: AsyncSession = Depends(get_db),
):
    """Get a subgraph centered on an entity, with configurable depth and predicate filtering.

    获取以某实体为中心的子图，可配置遍历深度和谓词过滤。"""
    entity = await get_entity(db, entity_id)
    if not entity:
        raise KGEntityNotFoundError(entity_id=entity_id)
    pred_list = [p.strip() for p in predicates.split(",") if p.strip()] if predicates else None
    graph = await get_entity_graph(db, entity_id, depth, max_nodes=max_nodes, predicates=pred_list)
    return graph


@router.get("/stats")
async def kg_stats(db: AsyncSession = Depends(get_db)):
    """Get knowledge graph statistics (entity and relation counts by type).

    获取知识图谱统计信息（各类型实体与关系数量）。"""
    return await get_kg_stats(db)


@router.get("/geo", response_model=KGGeoResponse)
async def get_kg_geo_entities(
    entity_type: str | None = Query(None, description="Comma-separated entity types"),
    year_start: int | None = None,
    year_end: int | None = None,
    south: float | None = None,
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    limit: int = Query(5000, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get geo-located knowledge graph entities for map display.

    获取具有地理坐标的知识图谱实体，用于地图展示。"""
    entity_types = (
        [t.strip() for t in entity_type.split(",") if t.strip()]
        if entity_type
        else None
    )
    bounds = None
    if all(v is not None for v in (south, west, north, east)):
        bounds = (south, west, north, east)  # type: ignore[arg-type]
    entities, total = await get_geo_entities(
        db, entity_types, year_start, year_end, bounds, limit
    )
    return KGGeoResponse(
        entities=[KGGeoEntity(**e) for e in entities],
        total=total,
    )


@router.get("/lineage-arcs", response_model=KGLineageArcsResponse)
async def get_kg_lineage_arcs(
    school: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    limit: int = Query(5000, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get teacher-student lineage arcs with coordinates for map visualization.

    获取师承传法弧线及坐标，用于地图可视化。"""
    arcs, total = await get_lineage_arcs(db, school, year_start, year_end, limit)
    return KGLineageArcsResponse(arcs=arcs, total=total)


@router.get("/texts/{text_id}/entities", response_model=list[KGEntityResponse])
async def list_text_entities(text_id: int, db: AsyncSession = Depends(get_db)):
    """List all knowledge graph entities linked to a specific text.

    列出与指定经文关联的所有知识图谱实体。"""
    entities = await get_text_entities(db, text_id)
    return [KGEntityResponse.model_validate(e) for e in entities]
