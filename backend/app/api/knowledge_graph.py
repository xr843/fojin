from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import KGEntityNotFoundError
from app.database import get_db
from app.schemas.knowledge_graph import (
    KGEntityDetailResponse,
    KGEntityResponse,
    KGGraphResponse,
    KGSearchResponse,
)
from app.services.knowledge_graph import (
    get_entity,
    get_entity_graph,
    get_entity_relations,
    get_kg_stats,
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
    entities, total = await search_entities(
        db, q, entity_type, limit, offset, has_relations=has_relations
    )
    return KGSearchResponse(
        total=total,
        results=[KGEntityResponse.model_validate(e) for e in entities],
    )


@router.get("/entities/{entity_id}", response_model=KGEntityDetailResponse)
async def get_kg_entity(entity_id: int, db: AsyncSession = Depends(get_db)):
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
    entity = await get_entity(db, entity_id)
    if not entity:
        raise KGEntityNotFoundError(entity_id=entity_id)
    pred_list = [p.strip() for p in predicates.split(",") if p.strip()] if predicates else None
    graph = await get_entity_graph(db, entity_id, depth, max_nodes=max_nodes, predicates=pred_list)
    return graph


@router.get("/stats")
async def kg_stats(db: AsyncSession = Depends(get_db)):
    return await get_kg_stats(db)


@router.get("/texts/{text_id}/entities", response_model=list[KGEntityResponse])
async def list_text_entities(text_id: int, db: AsyncSession = Depends(get_db)):
    entities = await get_text_entities(db, text_id)
    return [KGEntityResponse.model_validate(e) for e in entities]
