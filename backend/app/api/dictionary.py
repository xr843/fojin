from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.dictionary import DictionaryEntry

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


@router.get("/search")
async def search_dictionary(
    q: str = Query(..., min_length=1, description="搜索词条"),
    lang: str | None = Query(None, description="语言筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """搜索佛学辞典词条。"""
    stmt = select(DictionaryEntry).where(
        DictionaryEntry.headword.ilike(f"%{q}%")
    )
    if lang:
        stmt = stmt.where(DictionaryEntry.lang == lang)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    stmt = stmt.order_by(DictionaryEntry.headword).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    entries = result.scalars().all()

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
