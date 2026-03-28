from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user
from app.core.exceptions import TextNotFoundError
from app.database import get_db
from app.models.text import Text
from app.models.user import ReadingHistory, User
from app.schemas.text import JuanContentResponse, JuanLanguagesResponse, JuanListResponse, TextResponseBase
from app.services.content import get_juan_content, get_juan_languages, get_juan_list
from app.services.text import get_text_by_id, get_text_count

router = APIRouter(tags=["texts"])


@router.get("/texts/lookup-cbeta")
async def lookup_cbeta_ids(
    ids: str = Query(..., description="Comma-separated CBETA IDs"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Batch lookup CBETA IDs → text IDs. Returns {cbeta_id: text_id} for found entries."""
    cbeta_ids = [s.strip() for s in ids.split(",") if s.strip()][:500]
    if not cbeta_ids:
        return {}
    result = await db.execute(
        select(Text.cbeta_id, Text.id).where(Text.cbeta_id.in_(cbeta_ids))
    )
    return dict(result.all())


class SimilarPassageItem(BaseModel):
    text_id: int
    juan_num: int
    chunk_text: str
    score: float
    title_zh: str
    translator: str | None = None
    dynasty: str | None = None


class SimilarPassagesResponse(BaseModel):
    text_id: int
    juan_num: int
    passages: list[SimilarPassageItem]


@router.get("/texts/{text_id}", response_model=TextResponseBase)
async def get_text(text_id: int, db: AsyncSession = Depends(get_db)):
    """获取经典详情。"""
    text = await get_text_by_id(db, text_id)
    if not text:
        raise TextNotFoundError(text_id=text_id)
    return text


@router.get("/texts/{text_id}/juans", response_model=JuanListResponse)
async def list_juans(text_id: int, db: AsyncSession = Depends(get_db)):
    """获取经典的卷列表。"""
    result = await get_juan_list(db, text_id)
    if result is None:
        raise TextNotFoundError(text_id=text_id)
    return result


@router.get("/texts/{text_id}/juans/{juan_num}/languages", response_model=JuanLanguagesResponse)
async def juan_languages(text_id: int, juan_num: int, db: AsyncSession = Depends(get_db)):
    """获取某卷的可用语言列表。"""
    result = await get_juan_languages(db, text_id, juan_num)
    if result is None:
        raise TextNotFoundError(text_id=text_id)
    return result


@router.get("/texts/{text_id}/juans/{juan_num}", response_model=JuanContentResponse)
async def read_juan(
    text_id: int,
    juan_num: int,
    lang: str | None = Query(None, description="语言代码，如 pi、en、lzh"),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """获取经典某一卷的内容。登录用户自动记录阅读历史。"""
    result = await get_juan_content(db, text_id, juan_num, lang=lang)
    if result is None:
        raise TextNotFoundError(text_id=text_id)

    # Record reading history for logged-in users
    if user is not None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(ReadingHistory).values(
            user_id=user.id, text_id=text_id, juan_num=juan_num
        ).on_conflict_do_update(
            constraint="uq_reading_history_user_text",
            set_={"juan_num": juan_num, "last_read_at": datetime.now(UTC)},
        )
        await db.execute(stmt)
        await db.commit()

    return result


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """获取平台统计数据。"""
    count = await get_text_count(db)
    return {"total_texts": count}


@router.get("/texts/{text_id}/juans/{juan_num}/similar", response_model=SimilarPassagesResponse)
async def similar_passages(
    text_id: int,
    juan_num: int,
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """基于 pgvector 语义相似度，查找其他经典中的相似段落。"""
    # 1. Get the average embedding for this juan's chunks
    raw_conn = await db.connection()
    avg_result = await raw_conn.exec_driver_sql(
        "SELECT AVG(embedding)::text FROM text_embeddings "
        "WHERE text_id = $1 AND juan_num = $2 AND embedding IS NOT NULL",
        (text_id, juan_num),
    )
    avg_row = avg_result.fetchone()
    if not avg_row or avg_row[0] is None:
        return SimilarPassagesResponse(text_id=text_id, juan_num=juan_num, passages=[])

    avg_embedding_str = avg_row[0]

    # 2. Search for similar chunks in OTHER texts, deduplicate by text_id (keep highest score)
    search_result = await raw_conn.exec_driver_sql(
        "SELECT DISTINCT ON (te.text_id) "
        "te.text_id, te.juan_num, te.chunk_text, "
        "1 - (te.embedding <=> $1::vector) AS score, "
        "COALESCE(bt.title_zh, '') AS title_zh, "
        "bt.translator, bt.dynasty "
        "FROM text_embeddings te "
        "JOIN buddhist_texts bt ON bt.id = te.text_id "
        "WHERE te.text_id != $2 "
        "AND te.embedding IS NOT NULL "
        "AND 1 - (te.embedding <=> $1::vector) >= $3 "
        "ORDER BY te.text_id, te.embedding <=> $1::vector "
        "LIMIT 50",
        (avg_embedding_str, text_id, min_score),
    )
    rows = search_result.fetchall()

    # 3. Sort by score descending and take top N
    passages = sorted(
        [
            SimilarPassageItem(
                text_id=row[0],
                juan_num=row[1],
                chunk_text=row[2][:200],  # Truncate for display
                score=round(float(row[3]), 3),
                title_zh=row[4],
                translator=row[5],
                dynasty=row[6],
            )
            for row in rows
        ],
        key=lambda p: p.score,
        reverse=True,
    )[:limit]

    return SimilarPassagesResponse(text_id=text_id, juan_num=juan_num, passages=passages)
