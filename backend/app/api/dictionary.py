from fastapi import APIRouter, Depends, HTTPException, Query
from opencc import OpenCC
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.dictionary import DictionaryEntry

router = APIRouter(prefix="/dictionary", tags=["dictionary"])

_s2t = OpenCC("s2t")
_t2s = OpenCC("t2s")


def _zh_variants(q: str) -> list[str]:
    """Return deduplicated [original, simplified, traditional] variants."""
    return list({q, _t2s.convert(q), _s2t.convert(q)})


@router.get("/search")
async def search_dictionary(
    q: str = Query(..., min_length=1, max_length=200, description="搜索词条"),
    lang: str | None = Query(None, description="语言筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """搜索佛学辞典词条（词头 + 释义 + 读音），支持简繁互搜。"""
    variants = _zh_variants(q)
    # Build OR conditions for all variants (simplified + traditional)
    conditions = []
    for v in variants:
        like_v = f"%{v}%"
        conditions.append(DictionaryEntry.headword.ilike(like_v))
        conditions.append(DictionaryEntry.definition.ilike(like_v))
        conditions.append(DictionaryEntry.reading.ilike(like_v))
    filter_cond = or_(*conditions)
    stmt = select(DictionaryEntry).where(filter_cond)
    if lang:
        stmt = stmt.where(DictionaryEntry.lang == lang)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Relevance: exact headword (any variant) > substring headword > definition/reading
    exact_cases = [(DictionaryEntry.headword == v, 3) for v in variants]
    like_cases = [(DictionaryEntry.headword.ilike(f"%{v}%"), 2) for v in variants]
    relevance = case(*exact_cases, *like_cases, else_=1)

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
        "results": [
            {
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
            for e in entries
        ],
    }


@router.get("/{entry_id}")
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """获取辞典词条详情。"""
    result = await db.execute(
        select(DictionaryEntry)
        .options(joinedload(DictionaryEntry.source))
        .where(DictionaryEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="词条未找到")

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
