from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.source import DataSource, TextIdentifier
from app.models.text import BuddhistText, TextContent
from app.schemas.source import (
    DataSourceResponse,
    SourceDistributionListResponse,
    SourceDistributionResponse,
    TextIdentifierResponse,
)
from app.services.source import (
    get_all_sources,
    get_primary_ingest_distributions,
    get_source_by_code,
    get_source_distributions,
    get_text_identifiers,
)

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[DataSourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    sources = await get_all_sources(db)
    return sources


@router.get("/stats")
async def source_stats(db: AsyncSession = Depends(get_db)):
    """每个数据源的文本数、内容数、字符数统计（单次聚合查询）。"""
    text_counts = (
        select(
            BuddhistText.source_id,
            func.count(BuddhistText.id).label("text_count"),
        )
        .group_by(BuddhistText.source_id)
        .subquery()
    )

    ident_counts = (
        select(
            TextIdentifier.source_id,
            func.count(TextIdentifier.id).label("ident_count"),
        )
        .group_by(TextIdentifier.source_id)
        .subquery()
    )

    content_stats = (
        select(
            BuddhistText.source_id,
            func.count(TextContent.id).label("content_count"),
            func.coalesce(func.sum(TextContent.char_count), 0).label("char_count"),
        )
        .join(BuddhistText, TextContent.text_id == BuddhistText.id)
        .group_by(BuddhistText.source_id)
        .subquery()
    )

    stmt = (
        select(
            DataSource.code,
            DataSource.name_zh,
            DataSource.name_en,
            DataSource.is_active,
            func.coalesce(text_counts.c.text_count, 0).label("text_count"),
            func.coalesce(ident_counts.c.ident_count, 0).label("ident_count"),
            func.coalesce(content_stats.c.content_count, 0).label("content_count"),
            func.coalesce(content_stats.c.char_count, 0).label("char_count"),
        )
        .outerjoin(text_counts, DataSource.id == text_counts.c.source_id)
        .outerjoin(ident_counts, DataSource.id == ident_counts.c.source_id)
        .outerjoin(content_stats, DataSource.id == content_stats.c.source_id)
        .order_by(DataSource.id)
    )

    result = await db.execute(stmt)
    return [
        {
            "code": row.code,
            "name_zh": row.name_zh,
            "name_en": row.name_en,
            "text_count": row.text_count,
            "identifier_count": row.ident_count,
            "content_count": row.content_count,
            "char_count": int(row.char_count),
            "is_active": row.is_active,
        }
        for row in result.all()
    ]


@router.get("/texts/{text_id}/identifiers", response_model=list[TextIdentifierResponse])
async def list_text_identifiers(text_id: int, db: AsyncSession = Depends(get_db)):
    identifiers = await get_text_identifiers(db, text_id)
    return [
        TextIdentifierResponse(
            id=ident.id,
            source_id=ident.source_id,
            source_code=ident.source.code,
            source_name=ident.source.name_zh,
            source_uid=ident.source_uid,
            source_url=ident.source_url,
        )
        for ident in identifiers
    ]


@router.get("/ingest/primary", response_model=list[SourceDistributionListResponse])
async def list_primary_ingest_distributions(db: AsyncSession = Depends(get_db)):
    items = await get_primary_ingest_distributions(db)
    return [
        SourceDistributionListResponse(
            id=item.id,
            source_id=item.source_id,
            source_code=item.source.code,
            source_name=item.source.name_zh,
            code=item.code,
            name=item.name,
            channel_type=item.channel_type,
            url=item.url,
            format=item.format,
            license_note=item.license_note,
            is_primary_ingest=item.is_primary_ingest,
            priority=item.priority,
            is_active=item.is_active,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.get("/{code}/distributions", response_model=list[SourceDistributionResponse])
async def list_source_distributions(code: str, db: AsyncSession = Depends(get_db)):
    source = await get_source_by_code(db, code)
    if not source:
        raise HTTPException(status_code=404, detail="数据源未找到")
    return await get_source_distributions(db, code)


@router.get("/{code}", response_model=DataSourceResponse)
async def get_source(code: str, db: AsyncSession = Depends(get_db)):
    source = await get_source_by_code(db, code)
    if not source:
        raise HTTPException(status_code=404, detail="数据源未找到")
    return source
