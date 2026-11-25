from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.citation import CitationResponse
from app.services.citation import generate_citation
from app.services.machine_citation_api import build_cite_response

router = APIRouter(prefix="/citations", tags=["citations"])


@router.get("/text/{text_id}", response_model=CitationResponse)
async def get_citation(
    text_id: int,
    style: str = Query("chicago", description="引用格式: chicago/apa/mla/harvard"),
    db: AsyncSession = Depends(get_db),
):
    """生成指定文本的学术引用。"""
    return await generate_citation(db, text_id, style)


@router.get("/cite")
async def cite(
    urn: str | None = Query(
        None,
        max_length=300,
        description="fojin URN，如 `fojin:cbeta/T0374.14%230450a12`（`#` 要编码成 `%23`）",
    ),
    ref: str | None = Query(None, max_length=60, description="CBETA 行首，如 `T12n0374_p0450a12`"),
    quote: str | None = Query(None, max_length=500, description="可选：要放进引用里的原文"),
    db: AsyncSession = Depends(get_db),
):
    """机器可读引用：给一处经文位置（URN 或 CBETA 行首），返回可直接粘贴的中文引用、CBETA 行首、
    行级 URN、阅读器链接、BibTeX / RIS / CSL-JSON，以及这段文字的**许可与署名要求**。

    只给 URN 不带行号时只到卷。找不到经返回 404；URN 语法错误返回 422。"""
    return await build_cite_response(db, urn=urn, ref=ref, quote=quote)
