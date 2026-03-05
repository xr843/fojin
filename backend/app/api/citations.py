from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.citation import CitationResponse
from app.services.citation import generate_citation

router = APIRouter(prefix="/citations", tags=["citations"])


@router.get("/text/{text_id}", response_model=CitationResponse)
async def get_citation(
    text_id: int,
    style: str = Query("chicago", description="引用格式: chicago/apa/mla/harvard"),
    db: AsyncSession = Depends(get_db),
):
    """生成指定文本的学术引用。"""
    return await generate_citation(db, text_id, style)
