from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.relation import ParallelReadResponse, RelatedTextInfo, TextRelationsResponse
from app.services.relation import get_parallel_content, get_text_relations
from app.services.text import get_text_by_id

router = APIRouter(prefix="/texts", tags=["relations"])


@router.get("/{text_id}/relations", response_model=TextRelationsResponse)
async def list_text_relations(text_id: int, db: AsyncSession = Depends(get_db)):
    text = await get_text_by_id(db, text_id)
    if not text:
        raise HTTPException(status_code=404, detail="经典未找到")

    relations = await get_text_relations(db, text_id)
    return TextRelationsResponse(
        text_id=text.id,
        title_zh=text.title_zh,
        relations=[RelatedTextInfo(**r) for r in relations],
    )


@router.get("/{text_id}/parallel-read", response_model=ParallelReadResponse)
async def parallel_read(
    text_id: int,
    compare: int = Query(..., description="对照文本 ID"),
    juan: int = Query(1, description="卷号"),
    db: AsyncSession = Depends(get_db),
):
    result = await get_parallel_content(db, text_id, compare, juan)
    if not result:
        raise HTTPException(status_code=404, detail="对照内容未找到")
    return result
