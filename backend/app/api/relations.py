from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, TextNotFoundError
from app.database import get_db
from app.schemas.relation import ParallelReadResponse, RelatedTextInfo, TextRelationsResponse
from app.services.relation import get_parallel_content, get_text_relations
from app.services.text import get_text_by_id

router = APIRouter(prefix="/texts", tags=["relations"])


@router.get("/{text_id}/relations", response_model=TextRelationsResponse)
async def list_text_relations(
    text_id: int,
    relation_type: str | None = Query(None, description="Filter by relation type: cites, commentary, alt_translation, parallel / 按关系类型筛选"),
    db: AsyncSession = Depends(get_db),
):
    """List all relations of a text (citations, commentaries, translations, parallels).

    列出经文的所有关系（引用、注释、异译、平行文本）。"""
    text = await get_text_by_id(db, text_id)
    if not text:
        raise TextNotFoundError(text_id=text_id)

    relations = await get_text_relations(db, text_id)
    if relation_type:
        relations = [r for r in relations if r["relation_type"] == relation_type]
    return TextRelationsResponse(
        text_id=text.id,
        title_zh=text.title_zh,
        relations=[RelatedTextInfo(**r) for r in relations],
    )


@router.get("/{text_id}/parallel-read", response_model=ParallelReadResponse)
async def parallel_read(
    text_id: int,
    compare: int = Query(..., description="ID of the text to compare with / 对照文本 ID"),
    juan: int = Query(1, description="Juan (scroll) number / 卷号"),
    db: AsyncSession = Depends(get_db),
):
    """Side-by-side parallel reading of two related texts at a given juan.

    两部相关经文的平行对读。"""
    result = await get_parallel_content(db, text_id, compare, juan)
    if not result:
        raise NotFoundError("对照内容未找到")
    return result
