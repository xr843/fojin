"""Cross-canon alignment API.

Exposes the alignment_pairs table to the frontend Reader "多语对读" panel.
Given a chunk (text_id, juan_num, chunk_index), returns the aligned parallel
passages in other canons (lzh ↔ pi ↔ bo ↔ sa), each with full chunk_text and
source metadata for rendering.

Note on data provenance: for pi (SuttaCentral) and bo (84000) entries, the
chunk_text stored in text_embeddings is the English translation (Sujato /
84000). The real Pāli / Tibetan source, when available in text_contents, is
surfaced via original_preview so the panel can display both sides.
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
    original_preview: str | None = None
    original_lang: str | None = None


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


class CanonicalParallel(BaseModel):
    """Sutta-level academic parallel from SuttaCentral (stored in text_relations)."""
    related_text_id: int
    related_cbeta_id: str
    related_title: str
    related_lang: str
    relation_type: str
    note: str | None = None
    pali_preview: str | None = None
    english_preview: str | None = None


class CanonicalParallelsResponse(BaseModel):
    text_id: int
    source_cbeta_id: str
    source_title: str
    total: int
    parallels: list[CanonicalParallel]


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
            original_preview: str | None = None
            original_lang: str | None = None
            if other_lang in ("pi", "sa"):
                orig_row = (await db.execute(
                    sql_text(
                        "SELECT lang, LEFT(content, 500) FROM text_contents "
                        "WHERE text_id = :tid AND juan_num = :juan AND lang = :lang "
                        "LIMIT 1"
                    ),
                    {"tid": other_tid, "juan": other_juan, "lang": other_lang},
                )).fetchone()
                if orig_row and orig_row[1]:
                    original_lang = orig_row[0]
                    original_preview = orig_row[1]

            parallels.append(ParallelPair(
                text_id=other_tid,
                juan_num=other_juan,
                chunk_index=other_cidx,
                chunk_text=text_row[0],
                lang=other_lang or "lzh",
                title=text_row[1] or "",
                confidence=float(conf),
                original_preview=original_preview,
                original_lang=original_lang,
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


@router.get("/canonical/{text_id}", response_model=CanonicalParallelsResponse)
async def get_canonical_parallels(
    text_id: int,
    db: AsyncSession = Depends(get_db),
) -> CanonicalParallelsResponse:
    """Sutta-level SC parallels for a whole text.

    Reads text_relations (source='suttacentral') — authoritative Akanuma-style
    correspondences, no inference noise. For each parallel, also pulls the
    first ~240 chars of the related text's content (Pāli from text_contents,
    English from text_embeddings chunk 0) to preview in the panel.
    """
    src_row = (await db.execute(
        sql_text(
            "SELECT cbeta_id, title_zh FROM buddhist_texts WHERE id = :tid"
        ),
        {"tid": text_id},
    )).fetchone()
    if not src_row:
        return CanonicalParallelsResponse(
            text_id=text_id, source_cbeta_id="", source_title="", total=0, parallels=[]
        )

    rows = (await db.execute(
        sql_text("""
            SELECT
                CASE WHEN tr.text_a_id = :tid THEN tr.text_b_id ELSE tr.text_a_id END AS rel_id,
                tr.relation_type, tr.note
            FROM text_relations tr
            WHERE tr.source = 'suttacentral'
              AND (tr.text_a_id = :tid OR tr.text_b_id = :tid)
        """),
        {"tid": text_id},
    )).fetchall()

    parallels: list[CanonicalParallel] = []
    for rel_id, rel_type, note in rows:
        meta = (await db.execute(
            sql_text(
                "SELECT cbeta_id, "
                "COALESCE(title_pi, title_sa, title_en, title_zh, '') AS title, "
                "lang "
                "FROM buddhist_texts WHERE id = :rid"
            ),
            {"rid": rel_id},
        )).fetchone()
        if not meta:
            continue

        pali_preview: str | None = None
        english_preview: str | None = None
        if meta[2] == "pi":
            pi_row = (await db.execute(
                sql_text(
                    "SELECT LEFT(content, 240) FROM text_contents "
                    "WHERE text_id = :rid AND lang = 'pi' ORDER BY juan_num LIMIT 1"
                ),
                {"rid": rel_id},
            )).fetchone()
            if pi_row and pi_row[0]:
                pali_preview = pi_row[0]
            en_row = (await db.execute(
                sql_text(
                    "SELECT LEFT(chunk_text, 240) FROM text_embeddings "
                    "WHERE text_id = :rid ORDER BY juan_num, chunk_index LIMIT 1"
                ),
                {"rid": rel_id},
            )).fetchone()
            if en_row and en_row[0]:
                english_preview = en_row[0]

        parallels.append(CanonicalParallel(
            related_text_id=rel_id,
            related_cbeta_id=meta[0],
            related_title=meta[1] or "",
            related_lang=meta[2] or "",
            relation_type=rel_type,
            note=note,
            pali_preview=pali_preview,
            english_preview=english_preview,
        ))

    parallels.sort(key=lambda p: (0 if p.relation_type == "parallel" else 1, p.related_cbeta_id))

    return CanonicalParallelsResponse(
        text_id=text_id,
        source_cbeta_id=src_row[0],
        source_title=src_row[1] or "",
        total=len(parallels),
        parallels=parallels,
    )
