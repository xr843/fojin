from fastapi import APIRouter, Depends, Query
from opencc import OpenCC
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import DictionaryEntryNotFoundError
from app.database import get_db
from app.models.dictionary import DictionaryEntry
from app.models.source import DataSource

router = APIRouter(prefix="/dictionary", tags=["dictionary"])

_s2t = OpenCC("s2t")
_t2s = OpenCC("t2s")

HOT_TERMS = [
    "般若", "涅槃", "菩提", "缘起", "如来", "菩萨", "三昧", "慈悲", "佛性", "中道",
]


def _zh_variants(q: str) -> list[str]:
    """Return deduplicated [original, simplified, traditional] variants."""
    return list({q, _t2s.convert(q), _s2t.convert(q)})


def _build_search_conditions(variants: list[str]):
    """Build OR conditions for all variants (simplified + traditional)."""
    conditions = []
    for v in variants:
        like_v = f"%{v}%"
        conditions.append(DictionaryEntry.headword.ilike(like_v))
        conditions.append(DictionaryEntry.definition.ilike(like_v))
        conditions.append(DictionaryEntry.reading.ilike(like_v))
    return or_(*conditions)


def _build_relevance(variants: list[str]):
    """Build relevance scoring: exact headword > substring headword > definition/reading."""
    exact_cases = [(DictionaryEntry.headword == v, 3) for v in variants]
    like_cases = [(DictionaryEntry.headword.ilike(f"%{v}%"), 2) for v in variants]
    return case(*exact_cases, *like_cases, else_=1)


def _entry_to_dict(e: DictionaryEntry) -> dict:
    """Serialize a DictionaryEntry to response dict."""
    return {
        "id": e.id,
        "headword": e.headword,
        "reading": e.reading,
        "definition": e.definition,
        "lang": e.lang,
        "source_id": e.source_id,
        "source_code": e.source.code if e.source else None,
        "source_name": e.source.name_zh if e.source else None,
        "external_id": e.external_id,
    }


@router.get("/hot")
async def hot_terms():
    """Return popular Buddhist dictionary search terms for the landing page.

    返回辞典热门搜索词列表，用于首页展示。"""
    return {"terms": HOT_TERMS}


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    """List all dictionary sources with entry counts.

    返回所有辞典来源及其词条数量。"""
    # Subquery: count entries per source
    entry_counts = (
        select(DictionaryEntry.source_id, func.count().label("entry_count"))
        .group_by(DictionaryEntry.source_id)
        .subquery()
    )

    stmt = (
        select(DataSource, entry_counts.c.entry_count)
        .join(entry_counts, DataSource.id == entry_counts.c.source_id)
        .order_by(entry_counts.c.entry_count.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": src.id,
            "code": src.code,
            "name_zh": src.name_zh,
            "name_en": src.name_en,
            "description": src.description,
            "entry_count": count,
            "languages": [lang.strip() for lang in src.languages.split(",")] if src.languages else [],
            "base_url": src.base_url,
        }
        for src, count in rows
    ]


@router.get("/search/grouped")
async def search_dictionary_grouped(
    q: str = Query(..., min_length=1, max_length=200, description="搜索词条"),
    lang: str | None = Query(None, description="语言筛选"),
    source: str | None = Query(None, description="数据源 code 筛选"),
    size: int = Query(10, ge=1, le=50, description="每个来源返回的最大条数"),
    db: AsyncSession = Depends(get_db),
):
    """Search dictionary entries grouped by source. Supports simplified/traditional Chinese interconversion.

    按来源分组搜索辞典词条，支持简繁互搜。"""
    variants = _zh_variants(q)
    filter_cond = _build_search_conditions(variants)
    relevance = _build_relevance(variants)

    stmt = select(DictionaryEntry).where(filter_cond).options(joinedload(DictionaryEntry.source))
    if lang:
        stmt = stmt.where(DictionaryEntry.lang == lang)
    if source:
        stmt = stmt.join(DictionaryEntry.source).where(DataSource.code == source)

    # Count total
    count_stmt = select(func.count()).select_from(
        select(DictionaryEntry.id).where(filter_cond).subquery()
        if not lang and not source
        else stmt.with_only_columns(DictionaryEntry.id).subquery()
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # Fetch all matching entries ordered by relevance (capped for performance)
    stmt = stmt.order_by(
        relevance.desc(), func.length(DictionaryEntry.headword), DictionaryEntry.headword
    ).limit(500)
    result = await db.execute(stmt)
    entries = result.unique().scalars().all()

    # Group by source
    groups_map: dict[str, dict] = {}
    for e in entries:
        code = e.source.code if e.source else "_unknown"
        if code not in groups_map:
            groups_map[code] = {
                "source_code": code,
                "source_name_zh": e.source.name_zh if e.source else None,
                "entries": [],
            }
        if len(groups_map[code]["entries"]) < size:
            groups_map[code]["entries"].append(_entry_to_dict(e))

    return {
        "query": q,
        "total": total,
        "groups": list(groups_map.values()),
    }


@router.get("/search")
async def search_dictionary(
    q: str = Query(..., min_length=1, max_length=200, description="搜索词条"),
    lang: str | None = Query(None, description="语言筛选"),
    source: str | None = Query(None, description="数据源 code 筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search Buddhist dictionary entries by headword, definition, or reading. Supports simplified/traditional Chinese interconversion.

    搜索佛学辞典词条（词头 + 释义 + 读音），支持简繁互搜。"""
    variants = _zh_variants(q)
    filter_cond = _build_search_conditions(variants)

    stmt = select(DictionaryEntry).where(filter_cond)
    if lang:
        stmt = stmt.where(DictionaryEntry.lang == lang)
    if source:
        stmt = stmt.join(DictionaryEntry.source).where(DataSource.code == source)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Relevance ordering
    relevance = _build_relevance(variants)

    # Paginate with relevance ordering
    stmt = (
        stmt.options(joinedload(DictionaryEntry.source))
        .order_by(relevance.desc(), func.length(DictionaryEntry.headword), DictionaryEntry.headword)
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(stmt)
    entries = result.unique().scalars().all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "results": [_entry_to_dict(e) for e in entries],
    }


@router.get("/{entry_id}")
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Get full dictionary entry details including definition, reading, and source.

    获取辞典词条详情。"""
    result = await db.execute(
        select(DictionaryEntry)
        .options(joinedload(DictionaryEntry.source))
        .where(DictionaryEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise DictionaryEntryNotFoundError(entry_id=entry_id)

    return {
        "id": entry.id,
        "headword": entry.headword,
        "reading": entry.reading,
        "definition": entry.definition,
        "lang": entry.lang,
        "source_id": entry.source_id,
        "source_code": entry.source.code if entry.source else None,
        "source_name": entry.source.name_zh if entry.source else None,
        "entry_data": entry.entry_data,
        "external_id": entry.external_id,
        "created_at": entry.created_at.isoformat(),
    }
