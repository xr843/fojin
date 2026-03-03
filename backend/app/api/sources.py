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
    """每个数据源的文本数、内容数、字符数统计。"""
    # Get all sources
    sources = await get_all_sources(db, active_only=False)

    results = []
    for src in sources:
        # Count texts
        text_count_result = await db.execute(
            select(func.count(BuddhistText.id)).where(BuddhistText.source_id == src.id)
        )
        text_count = text_count_result.scalar() or 0

        # Count identifiers
        ident_count_result = await db.execute(
            select(func.count(TextIdentifier.id)).where(TextIdentifier.source_id == src.id)
        )
        ident_count = ident_count_result.scalar() or 0

        # Count contents and chars for texts from this source
        content_stats_result = await db.execute(
            select(
                func.count(TextContent.id),
                func.coalesce(func.sum(TextContent.char_count), 0),
            ).join(BuddhistText, TextContent.text_id == BuddhistText.id)
            .where(BuddhistText.source_id == src.id)
        )
        row = content_stats_result.one()
        content_count = row[0] or 0
        char_count = row[1] or 0

        results.append({
            "code": src.code,
            "name_zh": src.name_zh,
            "name_en": src.name_en,
            "text_count": text_count,
            "identifier_count": ident_count,
            "content_count": content_count,
            "char_count": int(char_count),
            "is_active": src.is_active,
        })

    return results


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
