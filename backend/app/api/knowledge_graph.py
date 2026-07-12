import asyncio
import base64
import gzip
import hashlib
import json
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import jittered_ttl
from app.core.exceptions import KGEntityNotFoundError
from app.database import get_db

KG_GEO_CACHE_TTL = 1800  # 30 min
KG_LINEAGE_CACHE_TTL = 1800
KG_STATS_CACHE_TTL = 3600  # 1 hour — recomputed on import, fine to be ~1h stale
KG_TIMELINE_CACHE_TTL = 3600
# HTTP caching for the heavy map payloads (/geo, /lineage-arcs). The data is
# already served up to ~30 min stale from Redis, so letting the browser/CDN
# reuse it for a few minutes is safe and makes a page refresh near-instant
# (browser cache / 304) instead of re-downloading ~2.6MB every time.
KG_MAP_HTTP_MAX_AGE = 600  # 10 min fresh in browser/CDN
KG_MAP_HTTP_SWR = 1800  # then serve-stale-while-revalidate up to 30 min
# Background warming for /geo. A cold recompute measured ~7s (two sequential
# scans of kg_entities + serializing ~65k rows), so without this the first
# visitor after every TTL lapse eats it. Warm well inside the 30 min TTL.
KG_GEO_WARM_INTERVAL = 1200  # 20 min
KG_GEO_WARM_LIMIT = 80000  # the exact shape the map page requests
from app.schemas.knowledge_graph import (
    KGEntityDetailResponse,
    KGEntityResponse,
    KGGeoEntity,
    KGGeoResponse,
    KGGraphResponse,
    KGLineageArcsResponse,
    KGMentionItem,
    KGMentionsResponse,
    KGSearchResponse,
    KGTimelineEntity,
    KGTimelineResponse,
)
from app.services.knowledge_graph import (
    get_entity,
    get_entity_graph,
    get_entity_relations,
    get_geo_entities,
    get_kg_stats,
    get_lineage_arcs,
    get_mentioned_entities,
    get_text_entities,
    get_timeline_entities,
    search_entities,
)

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])

logger = logging.getLogger(__name__)


def _gzip_bytes(payload_json: str) -> bytes:
    """Deterministic gzip (mtime=0): identical data → identical bytes → a stable
    ETag that survives cache expiry/recompute, so clients keep getting 304
    instead of re-downloading when the data hasn't actually changed."""
    return gzip.compress(payload_json.encode("utf-8"), compresslevel=6, mtime=0)


def _etag_of(gz: bytes) -> str:
    return 'W/"' + hashlib.sha1(gz).hexdigest() + '"'  # nosec B324 - cache validator, not security


def _etag_key(cache_key: str) -> str:
    """Tiny sibling key holding just the ETag, so a revalidating client can be
    answered with 304 without pulling and base64-decoding the ~2.3MB blob."""
    return cache_key + ":etag"


def _map_cache_headers(etag: str, max_age: int, swr: int) -> dict[str, str]:
    return {
        "ETag": etag,
        "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate={swr}",
        "Vary": "Accept-Encoding",
    }


async def _try_304(
    redis_client, cache_key: str, request: Request, max_age: int, swr: int
) -> Response | None:
    """Answer a conditional request from the tiny ETag key alone (cheap path)."""
    inm = request.headers.get("if-none-match")
    if not inm:
        return None
    cached_etag = await redis_client.get(_etag_key(cache_key))
    if cached_etag and cached_etag == inm:
        return Response(status_code=304, headers=_map_cache_headers(cached_etag, max_age, swr))
    return None


async def _store_gz(redis_client, cache_key: str, gz: bytes, ttl: int) -> None:
    """Cache gzip bytes as base64 (the redis client is decode_responses=True, so
    raw binary can't round-trip) plus the small sibling ETag key."""
    jttl = jittered_ttl(ttl)
    await redis_client.setex(cache_key, jttl, base64.b64encode(gz).decode("ascii"))
    await redis_client.setex(_etag_key(cache_key), jttl, _etag_of(gz))


def _map_response_from_gz(gz: bytes, request: Request, max_age: int, swr: int) -> Response:
    """Serve a pre-gzipped JSON blob with browser/CDN caching headers.

    Honors If-None-Match (304) and Accept-Encoding. Returning the bytes with
    Content-Encoding: gzip means nginx/CDN pass them through instead of
    re-compressing ~16MB on every request."""
    etag = _etag_of(gz)
    headers = _map_cache_headers(etag, max_age, swr)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        headers["Content-Encoding"] = "gzip"
        return Response(content=gz, media_type="application/json", headers=headers)
    # Rare client that doesn't accept gzip (e.g. bare curl): decompress on the fly.
    return Response(content=gzip.decompress(gz), media_type="application/json", headers=headers)


def _geo_cache_key(entity_types, year_start, year_end, bounds, limit) -> str:
    key_payload = json.dumps(
        {"t": entity_types, "ys": year_start, "ye": year_end, "b": bounds, "l": limit},
        sort_keys=True,
        separators=(",", ":"),
    )
    # `gz:` version prefix: values are gzip+base64, not the raw JSON stored by
    # earlier builds — a new prefix avoids misreading stale entries.
    return f"kg:geo:gz:{hashlib.sha1(key_payload.encode()).hexdigest()}"  # nosec B324


async def _build_geo_payload(db, entity_types, year_start, year_end, bounds, limit) -> str:
    """Build the /geo JSON, trimmed.

    Only 50 of ~65k geo entities have a year_start and 13 have a year_end, so
    emitting those (and the other mostly-null fields) as explicit nulls burned
    ~5.5MB of a ~16MB payload for nothing — exclude_none drops them. Rounding
    lat/lng to 5 decimals (~1m, far finer than a map dot needs) trims more.
    Raw JSON ~16MB → ~10.4MB; gzip barely shrinks (it already ate the repeated
    nulls), so the real win is browser JSON-parse time and memory."""
    entities, total = await get_geo_entities(
        db, entity_types, year_start, year_end, bounds, limit
    )
    for e in entities:
        if e.get("latitude") is not None:
            e["latitude"] = round(e["latitude"], 5)
        if e.get("longitude") is not None:
            e["longitude"] = round(e["longitude"], 5)
    response = KGGeoResponse(
        entities=[KGGeoEntity(**e) for e in entities],
        total=total,
    )
    return response.model_dump_json(exclude_none=True)


async def warm_kg_geo(redis) -> None:
    """Recompute the map's default /geo payload and refresh its cache, off the
    request path.

    Opens its own DB session (called from the lifespan loop, not a request).
    Best-effort: any failure is logged and swallowed so it never affects the app."""
    from app.database import async_session

    try:
        cache_key = _geo_cache_key(None, None, None, None, KG_GEO_WARM_LIMIT)
        async with async_session() as session:
            payload = await _build_geo_payload(
                session, None, None, None, None, KG_GEO_WARM_LIMIT
            )
        gz = _gzip_bytes(payload)
        await _store_gz(redis, cache_key, gz, KG_GEO_CACHE_TTL)
        logger.info("kg geo cache warmed: %d KB gzip", len(gz) // 1024)
    except Exception:
        logger.exception("kg geo warm failed")


async def kg_geo_warm_loop(redis) -> None:
    """Background task: warm /geo at startup, then every KG_GEO_WARM_INTERVAL.

    Keeps the cache populated so no real user pays the ~7s cold recompute.
    Cancelled on shutdown by the lifespan handler."""
    while True:
        await warm_kg_geo(redis)
        await asyncio.sleep(KG_GEO_WARM_INTERVAL)


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
    # relation_count isn't set on the detail path (search_entities computes
    # it via a degree subquery); derive it from the relations we just
    # fetched so the field isn't a misleading 0.
    base = KGEntityResponse.model_validate(entity).model_dump()
    base["relation_count"] = len(relations)
    return KGEntityDetailResponse(**base, relations=relations)


@router.get("/entities/{entity_id}/mentions", response_model=KGMentionsResponse)
async def get_kg_entity_mentions(
    entity_id: int,
    limit: int = Query(30, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
):
    """Return in-DB entities whose name appears in this entity's description.

    Used by the UI to provide a "描述中提及" panel when the structured
    kg_relations graph is sparse — common for DILA-imported persons whose
    only context is free-text description.  Inferred, not stored.

    返回该实体描述文本中提及的其它知识图谱实体，用于"描述中提及"面板，
    在 kg_relations 没有结构化关系时仍能给出可点击的语义关联。"""
    entity = await get_entity(db, entity_id)
    if not entity:
        raise KGEntityNotFoundError(entity_id=entity_id)
    mentions = await get_mentioned_entities(
        db, entity_id=entity_id, description=entity.description, limit=limit
    )
    return KGMentionsResponse(
        mentions=[KGMentionItem(**m) for m in mentions]
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
async def kg_stats(request: Request, db: AsyncSession = Depends(get_db)):
    """Get knowledge graph statistics (entity and relation counts by type).

    获取知识图谱统计信息（各类型实体与关系数量）。

    Cached: the underlying query is two full GROUP BY COUNT(*) scans over
    kg_entities/kg_relations and the result only changes when the KG is
    re-imported, so a ~1h cache is plenty and keeps the dashboard off the
    hot path."""
    redis_client = getattr(request.app.state, "redis", None)
    cache_key = "kg:stats"
    if redis_client:
        cached = await redis_client.get(cache_key)
        if cached:
            return Response(content=cached, media_type="application/json")
    stats = await get_kg_stats(db)
    payload = json.dumps(stats, ensure_ascii=False, default=str)
    if redis_client:
        await redis_client.setex(cache_key, jittered_ttl(KG_STATS_CACHE_TTL), payload)
    return Response(content=payload, media_type="application/json")


@router.get("/timeline", response_model=KGTimelineResponse)
async def get_kg_timeline(
    request: Request,
    entity_type: str | None = Query(
        None,
        description="Filter by entity type (e.g. 'person', 'dynasty'). Omit for all temporal entities.",
    ),
    limit: int = Query(500, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge graph entities with temporal data for timeline display.

    返回携带有效起始年份的知识图谱实体，用于时间轴可视化。BCE年份以负整数表示。

    Cached like /stats: scans kg_entities filtering on the JSON year fields
    and only changes on KG re-import."""
    redis_client = getattr(request.app.state, "redis", None)
    cache_key = None
    if redis_client:
        key_payload = json.dumps(
            {"t": entity_type, "l": limit}, sort_keys=True, separators=(",", ":")
        )
        cache_key = f"kg:timeline:{hashlib.sha1(key_payload.encode()).hexdigest()}"  # nosec B324
        cached = await redis_client.get(cache_key)
        if cached:
            return Response(content=cached, media_type="application/json")

    entities, total = await get_timeline_entities(db, entity_type, limit)
    response = KGTimelineResponse(
        entities=[KGTimelineEntity(**e) for e in entities],
        total=total,
    )
    payload = response.model_dump_json()
    if redis_client and cache_key:
        await redis_client.setex(cache_key, jittered_ttl(KG_TIMELINE_CACHE_TTL), payload)
    return Response(content=payload, media_type="application/json")


@router.get("/geo", response_model=KGGeoResponse)
async def get_kg_geo_entities(
    request: Request,
    entity_type: str | None = Query(None, description="Comma-separated entity types"),
    year_start: int | None = None,
    year_end: int | None = None,
    south: float | None = None,
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    limit: int = Query(200000, le=500000),
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

    redis_client = getattr(request.app.state, "redis", None)
    cache_key = None
    if redis_client:
        cache_key = _geo_cache_key(entity_types, year_start, year_end, bounds, limit)
        not_modified = await _try_304(
            redis_client, cache_key, request, KG_MAP_HTTP_MAX_AGE, KG_MAP_HTTP_SWR
        )
        if not_modified is not None:
            return not_modified
        cached = await redis_client.get(cache_key)
        if cached:
            return _map_response_from_gz(
                base64.b64decode(cached), request, KG_MAP_HTTP_MAX_AGE, KG_MAP_HTTP_SWR
            )

    payload = await _build_geo_payload(
        db, entity_types, year_start, year_end, bounds, limit
    )
    gz = _gzip_bytes(payload)
    if redis_client and cache_key:
        await _store_gz(redis_client, cache_key, gz, KG_GEO_CACHE_TTL)
    return _map_response_from_gz(gz, request, KG_MAP_HTTP_MAX_AGE, KG_MAP_HTTP_SWR)


@router.get("/lineage-arcs", response_model=KGLineageArcsResponse)
async def get_kg_lineage_arcs(
    request: Request,
    school: str | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    limit: int = Query(200000, le=500000),
    db: AsyncSession = Depends(get_db),
):
    """Get teacher-student lineage arcs with coordinates for map visualization.

    获取师承传法弧线及坐标，用于地图可视化。"""
    redis_client = getattr(request.app.state, "redis", None)
    cache_key = None
    if redis_client:
        key_payload = json.dumps(
            {"s": school, "ys": year_start, "ye": year_end, "l": limit},
            sort_keys=True,
            separators=(",", ":"),
        )
        cache_key = f"kg:lineage:gz:{hashlib.sha1(key_payload.encode()).hexdigest()}"  # nosec B324
        not_modified = await _try_304(
            redis_client, cache_key, request, KG_MAP_HTTP_MAX_AGE, KG_MAP_HTTP_SWR
        )
        if not_modified is not None:
            return not_modified
        cached = await redis_client.get(cache_key)
        if cached:
            return _map_response_from_gz(
                base64.b64decode(cached), request, KG_MAP_HTTP_MAX_AGE, KG_MAP_HTTP_SWR
            )

    arcs, total = await get_lineage_arcs(db, school, year_start, year_end, limit)
    response = KGLineageArcsResponse(arcs=arcs, total=total)
    # Deliberately NOT exclude_none here (unlike /geo): the map's arc filter and
    # tooltip test `arc.year === null`, so arcs must keep explicit nulls. The
    # arcs payload is small anyway (~8k rows, only fetched when 师承 is ticked).
    gz = _gzip_bytes(response.model_dump_json())
    if redis_client and cache_key:
        await _store_gz(redis_client, cache_key, gz, KG_LINEAGE_CACHE_TTL)
    return _map_response_from_gz(gz, request, KG_MAP_HTTP_MAX_AGE, KG_MAP_HTTP_SWR)


@router.get("/texts/{text_id}/entities", response_model=list[KGEntityResponse])
async def list_text_entities(text_id: int, db: AsyncSession = Depends(get_db)):
    """List all knowledge graph entities linked to a specific text.

    列出与指定经文关联的所有知识图谱实体。"""
    entities = await get_text_entities(db, text_id)
    return [KGEntityResponse.model_validate(e) for e in entities]
