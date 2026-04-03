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


def _build_exact_prefix_conditions(variants: list[str]):
    """Build conditions for exact match + prefix match (fast, uses btree index)."""
    conditions = []
    for v in variants:
        conditions.append(DictionaryEntry.headword == v)
        conditions.append(DictionaryEntry.headword.ilike(f"{v}%"))
    return or_(*conditions)


def _build_substring_conditions(variants: list[str]):
    """Build conditions for substring match (slower, uses trgm index)."""
    conditions = []
    for v in variants:
        conditions.append(DictionaryEntry.headword.ilike(f"%{v}%"))
    return or_(*conditions)


def _build_relevance(variants: list[str]):
    """Build relevance scoring: exact headword > prefix > substring."""
    exact_cases = [(DictionaryEntry.headword == v, 3) for v in variants]
    prefix_cases = [(DictionaryEntry.headword.ilike(f"{v}%"), 2) for v in variants]
    return case(*exact_cases, *prefix_cases, else_=1)


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
        .order_by(DataSource.sort_order, entry_counts.c.entry_count.desc())
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

    按来源分组搜索辞典词条，支持简繁互搜。
    Two-phase search: first exact+prefix (fast), then substring if needed."""
    variants = _zh_variants(q)
    relevance = _build_relevance(variants)

    # Phase 1: exact + prefix match (fast, uses btree index)
    fast_cond = _build_exact_prefix_conditions(variants)
    base_filters = []
    if lang:
        base_filters.append(DictionaryEntry.lang == lang)
    if source:
        base_filters.append(DataSource.code == source)

    stmt = select(DictionaryEntry).where(fast_cond, *base_filters).options(joinedload(DictionaryEntry.source))
    if source:
        stmt = stmt.join(DictionaryEntry.source)
    stmt = stmt.order_by(relevance.desc(), func.length(DictionaryEntry.headword), DictionaryEntry.headword).limit(200)
    result = await db.execute(stmt)
    entries = list(result.unique().scalars().all())
    total = len(entries)

    # Phase 2: substring match only if phase 1 found very few results
    if total < 5:
        sub_cond = _build_substring_conditions(variants)
        stmt2 = select(DictionaryEntry).where(sub_cond, *base_filters).options(joinedload(DictionaryEntry.source))
        if source:
            stmt2 = stmt2.join(DictionaryEntry.source)
        stmt2 = stmt2.order_by(relevance.desc(), func.length(DictionaryEntry.headword)).limit(200)
        result2 = await db.execute(stmt2)
        seen_ids = {e.id for e in entries}
        for e in result2.unique().scalars().all():
            if e.id not in seen_ids:
                entries.append(e)
                seen_ids.add(e.id)
        total = len(entries)

    # Group by source
    groups_map: dict[str, dict] = {}
    for e in entries:
        code = e.source.code if e.source else "_unknown"
        if code not in groups_map:
            name = e.source.name_zh if e.source else None
            groups_map[code] = {
                "source_code": code,
                "source_name": name,
                "source_name_zh": name,
                "sort_order": e.source.sort_order if e.source else 9999,
                "entries": [],
                "total": 0,
            }
        groups_map[code]["total"] += 1
        if len(groups_map[code]["entries"]) < size:
            groups_map[code]["entries"].append(_entry_to_dict(e))

    # Sort groups by source sort_order (lower = higher priority)
    sorted_groups = sorted(groups_map.values(), key=lambda g: g["sort_order"])

    return {
        "query": q,
        "total": total,
        "groups": sorted_groups,
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
    """Search Buddhist dictionary entries by headword. Supports simplified/traditional Chinese interconversion.

    搜索佛学辞典词条（词头匹配），支持简繁互搜。"""
    variants = _zh_variants(q)
    fast_cond = _build_exact_prefix_conditions(variants)
    relevance = _build_relevance(variants)

    base_filters = []
    if lang:
        base_filters.append(DictionaryEntry.lang == lang)

    stmt = select(DictionaryEntry).where(fast_cond, *base_filters)
    if source:
        stmt = stmt.join(DictionaryEntry.source).where(DataSource.code == source)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

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
