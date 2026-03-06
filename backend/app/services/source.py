from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.source import DataSource, SourceDistribution, TextIdentifier


async def get_all_sources(session: AsyncSession, active_only: bool = True) -> list[DataSource]:
    stmt = (
        select(DataSource)
        .options(selectinload(DataSource.distributions))
        .order_by(DataSource.sort_order)
    )
    if active_only:
        stmt = stmt.where(DataSource.is_active == True)
    result = await session.execute(stmt)
    sources = list(result.scalars().all())
    for source in sources:
        source.distributions.sort(key=lambda item: (item.priority, item.id))
    return sources


async def get_source_by_code(session: AsyncSession, code: str) -> DataSource | None:
    result = await session.execute(
        select(DataSource)
        .options(selectinload(DataSource.distributions))
        .where(DataSource.code == code)
    )
    source = result.scalar_one_or_none()
    if source:
        source.distributions.sort(key=lambda item: (item.priority, item.id))
    return source


async def get_text_identifiers(session: AsyncSession, text_id: int) -> list[TextIdentifier]:
    result = await session.execute(
        select(TextIdentifier)
        .options(joinedload(TextIdentifier.source))
        .where(TextIdentifier.text_id == text_id)
        .order_by(TextIdentifier.source_id.asc(), TextIdentifier.id.asc())
    )
    return list(result.scalars().all())


async def get_source_distributions(
    session: AsyncSession,
    code: str,
    active_only: bool = True,
) -> list[SourceDistribution]:
    stmt = (
        select(SourceDistribution)
        .join(SourceDistribution.source)
        .options(joinedload(SourceDistribution.source))
        .where(DataSource.code == code)
        .order_by(SourceDistribution.priority.asc(), SourceDistribution.id.asc())
    )
    if active_only:
        stmt = stmt.where(SourceDistribution.is_active == True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_primary_ingest_distributions(
    session: AsyncSession,
    active_only: bool = True,
) -> list[SourceDistribution]:
    stmt = (
        select(SourceDistribution)
        .options(joinedload(SourceDistribution.source))
        .where(SourceDistribution.is_primary_ingest == True)
        .order_by(SourceDistribution.priority.asc(), SourceDistribution.id.asc())
    )
    if active_only:
        stmt = stmt.where(SourceDistribution.is_active == True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_source_text_count(session: AsyncSession, source_id: int) -> int:
    from sqlalchemy import func
    from app.models.text import BuddhistText
    result = await session.execute(
        select(func.count(BuddhistText.id)).where(BuddhistText.source_id == source_id)
    )
    return result.scalar() or 0
