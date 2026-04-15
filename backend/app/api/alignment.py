"""Cross-canon alignment API.

Exposes the alignment_pairs table to the frontend Reader "他藏对读" tab.
Given a chunk (text_id, juan_num, chunk_index), returns the aligned parallel
passages in other canons (lzh ↔ pi ↔ bo), each with full chunk_text and
source metadata for rendering.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/alignment", tags=["alignment"])


class ParallelPair(BaseModel):
    """One aligned parallel passage."""
    text_id: int
    juan_num: int
    chunk_index: int
    chunk_text: str
    lang: str
    title: str = ""
    confidence: float = 1.0


class ChunkAlignmentResponse(BaseModel):
    """All parallels for one source chunk."""
    source_text_id: int
    source_juan_num: int
    source_chunk_index: int
    parallels: list[ParallelPair]


class JuanAlignmentEntry(BaseModel):
    """One chunk inside a juan + its parallels (for Reader sidebar rendering)."""
    chunk_index: int
    chunk_text: str
    parallels: list[ParallelPair]


class JuanAlignmentResponse(BaseModel):
    text_id: int
    juan_num: int
    total_chunks: int
    chunks_with_parallels: int
    entries: list[JuanAlignmentEntry]


@router.get("/chunks/{text_id}/{juan_num}/{chunk_index}", response_model=ChunkAlignmentResponse)
async def get_chunk_alignment(
    text_id: int,
    juan_num: int,
    chunk_index: int,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> ChunkAlignmentResponse:
    """Get all aligned parallels for a single chunk.

    Checks both sides of alignment_pairs (text_a_* and text_b_*) so the
    alignment is direction-agnostic.
    """
    rows = (await db.execute(
        sql_text("""
            SELECT
                CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                     THEN ap.text_b_id ELSE ap.text_a_id END,
                CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                     THEN ap.text_b_juan_num ELSE ap.text_a_juan_num END,
                CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                     THEN ap.text_b_chunk_index ELSE ap.text_a_chunk_index END,
                CASE WHEN ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx
                     THEN ap.text_b_lang ELSE ap.text_a_lang END,
                ap.confidence
            FROM alignment_pairs ap
            WHERE (
                (ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx)
                OR
                (ap.text_b_id = :tid AND ap.text_b_juan_num = :juan AND ap.text_b_chunk_index = :cidx)
            )
            AND ap.text_a_chunk_index IS NOT NULL
            ORDER BY ap.confidence DESC
            LIMIT :limit
        """),
        {"tid": text_id, "juan": juan_num, "cidx": chunk_index, "limit": limit},
    )).fetchall()

    parallels: list[ParallelPair] = []
    for row in rows:
        other_tid, other_juan, other_cidx, other_lang, conf = row
        text_row = (await db.execute(
            sql_text(
                "SELECT te.chunk_text, "
                "COALESCE(bt.title_zh, bt.title_sa, bt.title_pi, bt.title_en, '') "
                "FROM text_embeddings te "
                "LEFT JOIN buddhist_texts bt ON bt.id = te.text_id "
                "WHERE te.text_id = :tid AND te.juan_num = :juan AND te.chunk_index = :cidx"
            ),
            {"tid": other_tid, "juan": other_juan, "cidx": other_cidx},
        )).fetchone()
        if text_row:
            parallels.append(ParallelPair(
                text_id=other_tid,
                juan_num=other_juan,
                chunk_index=other_cidx,
                chunk_text=text_row[0],
                lang=other_lang or "lzh",
                title=text_row[1] or "",
                confidence=float(conf),
            ))

    return ChunkAlignmentResponse(
        source_text_id=text_id,
        source_juan_num=juan_num,
        source_chunk_index=chunk_index,
        parallels=parallels,
    )


@router.get("/texts/{text_id}/juans/{juan_num}", response_model=JuanAlignmentResponse)
async def get_juan_alignment(
    text_id: int,
    juan_num: int,
    db: AsyncSession = Depends(get_db),
) -> JuanAlignmentResponse:
    """Get all chunks of a juan that have any alignment parallels.

    Used by Reader's "他藏对读" panel to show a segment-by-segment index of
    which paragraphs in this juan have parallel passages in other canons.
    Chunks without any alignment are omitted from entries but counted in
    total_chunks for UX progress display.
    """
    # Count total chunks in this juan
    total_row = (await db.execute(
        sql_text(
            "SELECT COUNT(*) FROM text_embeddings "
            "WHERE text_id = :tid AND juan_num = :juan"
        ),
        {"tid": text_id, "juan": juan_num},
    )).fetchone()
    total_chunks = int(total_row[0]) if total_row else 0

    # Get chunks that have alignments (either direction)
    rows = (await db.execute(
        sql_text("""
            SELECT DISTINCT te.chunk_index, te.chunk_text
            FROM text_embeddings te
            WHERE te.text_id = :tid AND te.juan_num = :juan
            AND EXISTS (
                SELECT 1 FROM alignment_pairs ap
                WHERE ap.text_a_chunk_index IS NOT NULL
                AND (
                    (ap.text_a_id = te.text_id AND ap.text_a_juan_num = te.juan_num AND ap.text_a_chunk_index = te.chunk_index)
                    OR
                    (ap.text_b_id = te.text_id AND ap.text_b_juan_num = te.juan_num AND ap.text_b_chunk_index = te.chunk_index)
                )
            )
            ORDER BY te.chunk_index
        """),
        {"tid": text_id, "juan": juan_num},
    )).fetchall()

    entries: list[JuanAlignmentEntry] = []
    for chunk_idx, chunk_text in rows:
        alignment_resp = await get_chunk_alignment(text_id, juan_num, chunk_idx, 5, db)
        entries.append(JuanAlignmentEntry(
            chunk_index=chunk_idx,
            chunk_text=chunk_text,
            parallels=alignment_resp.parallels,
        ))

    return JuanAlignmentResponse(
        text_id=text_id,
        juan_num=juan_num,
        total_chunks=total_chunks,
        chunks_with_parallels=len(entries),
        entries=entries,
    )
