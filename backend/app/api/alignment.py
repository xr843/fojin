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
from sqlalchemy import bindparam
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/alignment", tags=["alignment"])

# A fojin chunk (paragraph) can contain many MITRA sentence-level parallels;
# cap per chunk so the reader panel stays bounded on dense texts.
MITRA_CHUNK_LIMIT = 50

# Per-chunk cap on fojin↔fojin parallels in the juan index, matching the
# single-chunk endpoint's default limit.
PAIR_LIMIT = 5


class ParallelPair(BaseModel):
    """One aligned parallel passage.

    source="fojin": both sides are fojin chunks (from alignment_pairs); text_id/
    juan_num/chunk_index deep-link to the counterpart in the reader.
    source="mitra-parallel": the foreign side is an inline Sanskrit/Tibetan
    sentence from MITRA (CC BY-SA 4.0) with no fojin chunk — chunk_text holds the
    foreign text and text_id/juan_num/chunk_index are 0 (no deep-link target).
    """
    text_id: int
    juan_num: int
    chunk_index: int
    chunk_text: str
    lang: str
    title: str = ""
    confidence: float = 1.0
    original_preview: str | None = None
    original_lang: str | None = None
    source: str = "fojin"


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


class FullParallelContentResponse(BaseModel):
    text_id: int
    cbeta_id: str
    title: str
    lang: str
    pali_full: str | None = None
    english_full: str | None = None
    pali_chars: int = 0
    english_chars: int = 0


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

    # MITRA cross-lingual parallels (inline Sanskrit/Tibetan, CC BY-SA 4.0).
    # The foreign side has no fojin chunk, so chunk_text carries the foreign
    # sentence and the deep-link ids are 0. A fojin chunk (a paragraph) can hold
    # many MITRA sentence-pairs, so this uses its own larger cap.
    mitra_rows = (await db.execute(
        sql_text(
            "SELECT foreign_text, foreign_lang, confidence "
            "FROM mitra_alignments "
            "WHERE text_id = :tid AND juan_num = :juan AND chunk_index = :cidx "
            "ORDER BY foreign_lang, id LIMIT :limit"
        ),
        {"tid": text_id, "juan": juan_num, "cidx": chunk_index, "limit": MITRA_CHUNK_LIMIT},
    )).fetchall()
    for foreign_text, foreign_lang, conf in mitra_rows:
        parallels.append(ParallelPair(
            text_id=0,
            juan_num=0,
            chunk_index=0,
            chunk_text=foreign_text,
            lang=foreign_lang or "sa",
            title="MITRA 平行（藏）" if foreign_lang == "bo" else "MITRA 平行（梵）",
            confidence=float(conf) if conf is not None else 1.0,
            source="mitra-parallel",
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

    Used by Reader's "多语对读" panel to show a segment-by-segment index of
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
            AND (
                EXISTS (
                    SELECT 1 FROM alignment_pairs ap
                    WHERE ap.text_a_chunk_index IS NOT NULL
                    AND (
                        (ap.text_a_id = te.text_id AND ap.text_a_juan_num = te.juan_num AND ap.text_a_chunk_index = te.chunk_index)
                        OR
                        (ap.text_b_id = te.text_id AND ap.text_b_juan_num = te.juan_num AND ap.text_b_chunk_index = te.chunk_index)
                    )
                )
                OR EXISTS (
                    SELECT 1 FROM mitra_alignments ma
                    WHERE ma.text_id = te.text_id AND ma.juan_num = te.juan_num
                    AND ma.chunk_index = te.chunk_index
                )
            )
            ORDER BY te.chunk_index
        """),
        {"tid": text_id, "juan": juan_num},
    )).fetchall()

    chunk_list = [(int(r[0]), r[1]) for r in rows]
    if not chunk_list:
        return JuanAlignmentResponse(
            text_id=text_id,
            juan_num=juan_num,
            total_chunks=total_chunks,
            chunks_with_parallels=0,
            entries=[],
        )
    cidxs = [c[0] for c in chunk_list]

    # --- Batched fetch (replaces the old per-chunk get_chunk_alignment N+1) ---
    # The juan panel used to call get_chunk_alignment once per chunk, each
    # firing up to ~12 queries (1 pairs + ≤5 chunk lookups + ≤5 previews + 1
    # MITRA). That was O(chunks) round-trips. The block below fetches the whole
    # juan in a constant ~4 set-based queries and assembles in Python.
    #
    # alignment_pairs has zero intra-text/intra-juan rows (verified), so every
    # qualifying pair matches exactly one side; a single CASE selects the source
    # chunk and its counterpart. ROW_NUMBER caps each source chunk at PAIR_LIMIT
    # by confidence, mirroring get_chunk_alignment's per-chunk LIMIT.
    pair_rows = (await db.execute(
        sql_text("""
            WITH base AS (
                SELECT ap.text_a_id, ap.text_a_juan_num, ap.text_a_chunk_index, ap.text_a_lang,
                       ap.text_b_id, ap.text_b_juan_num, ap.text_b_chunk_index, ap.text_b_lang,
                       ap.confidence,
                       (ap.text_a_id = :tid AND ap.text_a_juan_num = :juan
                        AND ap.text_a_chunk_index = ANY(:cidxs)) AS a_is_src
                FROM alignment_pairs ap
                WHERE ap.text_a_chunk_index IS NOT NULL
                  AND (
                    (ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = ANY(:cidxs))
                    OR
                    (ap.text_b_id = :tid AND ap.text_b_juan_num = :juan AND ap.text_b_chunk_index = ANY(:cidxs))
                  )
            ),
            matched AS (
                SELECT
                    CASE WHEN a_is_src THEN text_a_chunk_index ELSE text_b_chunk_index END AS source_cidx,
                    CASE WHEN a_is_src THEN text_b_id ELSE text_a_id END AS other_tid,
                    CASE WHEN a_is_src THEN text_b_juan_num ELSE text_a_juan_num END AS other_juan,
                    CASE WHEN a_is_src THEN text_b_chunk_index ELSE text_a_chunk_index END AS other_cidx,
                    CASE WHEN a_is_src THEN text_b_lang ELSE text_a_lang END AS other_lang,
                    confidence
                FROM base
            )
            SELECT source_cidx, other_tid, other_juan, other_cidx, other_lang, confidence
            FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY source_cidx ORDER BY confidence DESC
                ) AS rn
                FROM matched
            ) t
            WHERE rn <= :pair_limit
            ORDER BY source_cidx, confidence DESC
        """),
        {"tid": text_id, "juan": juan_num, "cidxs": cidxs, "pair_limit": PAIR_LIMIT},
    )).fetchall()

    pairs_by_src: dict[int, list] = {}
    te_keys: set[tuple] = set()
    tc_keys: set[tuple] = set()
    for source_cidx, other_tid, other_juan, other_cidx, other_lang, conf in pair_rows:
        pairs_by_src.setdefault(source_cidx, []).append(
            (other_tid, other_juan, other_cidx, other_lang, conf)
        )
        te_keys.add((other_tid, other_juan, other_cidx))
        if other_lang in ("pi", "sa"):
            tc_keys.add((other_tid, other_juan, other_lang))

    # Batched chunk_text + title for every counterpart chunk.
    te_map: dict[tuple, tuple] = {}
    if te_keys:
        te_rows = (await db.execute(
            sql_text("""
                SELECT te.text_id, te.juan_num, te.chunk_index, te.chunk_text,
                       COALESCE(bt.title_zh, bt.title_sa, bt.title_pi, bt.title_en, '')
                FROM text_embeddings te
                LEFT JOIN buddhist_texts bt ON bt.id = te.text_id
                WHERE (te.text_id, te.juan_num, te.chunk_index) IN :keys
            """).bindparams(bindparam("keys", expanding=True)),
            {"keys": list(te_keys)},
        )).fetchall()
        for tid_, juan_, cidx_, ctext, title in te_rows:
            te_map[(tid_, juan_, cidx_)] = (ctext, title)

    # Batched original-language preview for pi/sa counterparts.
    tc_map: dict[tuple, tuple] = {}
    if tc_keys:
        tc_rows = (await db.execute(
            sql_text("""
                SELECT DISTINCT ON (text_id, juan_num, lang)
                       text_id, juan_num, lang, LEFT(content, 500)
                FROM text_contents
                WHERE (text_id, juan_num, lang) IN :triples
                ORDER BY text_id, juan_num, lang
            """).bindparams(bindparam("triples", expanding=True)),
            {"triples": list(tc_keys)},
        )).fetchall()
        for tid_, juan_, lang_, preview in tc_rows:
            if preview:
                tc_map[(tid_, juan_, lang_)] = (lang_, preview)

    # Batched MITRA cross-lingual parallels, capped per chunk (mirrors the
    # single-chunk endpoint's MITRA_CHUNK_LIMIT and foreign_lang, id ordering).
    mitra_by_src: dict[int, list] = {}
    mitra_rows = (await db.execute(
        sql_text("""
            SELECT chunk_index, foreign_text, foreign_lang, confidence
            FROM (
                SELECT chunk_index, foreign_text, foreign_lang, confidence,
                       ROW_NUMBER() OVER (
                           PARTITION BY chunk_index ORDER BY foreign_lang, id
                       ) AS rn
                FROM mitra_alignments
                WHERE text_id = :tid AND juan_num = :juan AND chunk_index = ANY(:cidxs)
            ) t
            WHERE rn <= :mlimit
            ORDER BY chunk_index, rn
        """),
        {"tid": text_id, "juan": juan_num, "cidxs": cidxs, "mlimit": MITRA_CHUNK_LIMIT},
    )).fetchall()
    for chunk_index, foreign_text, foreign_lang, conf in mitra_rows:
        mitra_by_src.setdefault(chunk_index, []).append(
            (foreign_text, foreign_lang, conf)
        )

    # Assemble entries in chunk order: fojin parallels first (confidence desc),
    # then MITRA — the same per-chunk shape get_chunk_alignment produces.
    entries: list[JuanAlignmentEntry] = []
    for chunk_idx, chunk_text in chunk_list:
        parallels: list[ParallelPair] = []
        for other_tid, other_juan, other_cidx, other_lang, conf in pairs_by_src.get(chunk_idx, []):
            te = te_map.get((other_tid, other_juan, other_cidx))
            if not te:
                continue
            ctext, title = te
            original_preview = None
            original_lang = None
            if other_lang in ("pi", "sa"):
                tc = tc_map.get((other_tid, other_juan, other_lang))
                if tc:
                    original_lang, original_preview = tc
            parallels.append(ParallelPair(
                text_id=other_tid,
                juan_num=other_juan,
                chunk_index=other_cidx,
                chunk_text=ctext,
                lang=other_lang or "lzh",
                title=title or "",
                confidence=float(conf),
                original_preview=original_preview,
                original_lang=original_lang,
            ))
        for foreign_text, foreign_lang, conf in mitra_by_src.get(chunk_idx, []):
            parallels.append(ParallelPair(
                text_id=0,
                juan_num=0,
                chunk_index=0,
                chunk_text=foreign_text,
                lang=foreign_lang or "sa",
                title="MITRA 平行（藏）" if foreign_lang == "bo" else "MITRA 平行（梵）",
                confidence=float(conf) if conf is not None else 1.0,
                source="mitra-parallel",
            ))
        entries.append(JuanAlignmentEntry(
            chunk_index=chunk_idx,
            chunk_text=chunk_text,
            parallels=parallels,
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


@router.get("/canonical/full/{text_id}", response_model=FullParallelContentResponse)
async def get_full_parallel_content(
    text_id: int,
    db: AsyncSession = Depends(get_db),
) -> FullParallelContentResponse:
    """Lazy-load full Pāli + English for one parallel sutta.

    Called when user expands a card in 按经对读 panel and wants to see the
    complete alignment (not just 240-char preview).

    Pāli: concatenates all text_contents.content rows (in juan order) for lang='pi'.
    English: concatenates all text_embeddings.chunk_text rows in order.
    """
    meta = (await db.execute(
        sql_text(
            "SELECT cbeta_id, "
            "COALESCE(title_pi, title_sa, title_en, title_zh, '') AS title, "
            "lang "
            "FROM buddhist_texts WHERE id = :tid"
        ),
        {"tid": text_id},
    )).fetchone()
    if not meta:
        return FullParallelContentResponse(
            text_id=text_id, cbeta_id="", title="", lang="",
        )

    pali_rows = (await db.execute(
        sql_text(
            "SELECT content FROM text_contents "
            "WHERE text_id = :tid AND lang = 'pi' ORDER BY juan_num"
        ),
        {"tid": text_id},
    )).fetchall()
    pali_full = "\n\n".join(r[0] for r in pali_rows if r[0]) if pali_rows else None

    en_rows = (await db.execute(
        sql_text(
            "SELECT chunk_text FROM text_embeddings "
            "WHERE text_id = :tid ORDER BY juan_num, chunk_index"
        ),
        {"tid": text_id},
    )).fetchall()
    english_full = "\n\n".join(r[0] for r in en_rows if r[0]) if en_rows else None

    return FullParallelContentResponse(
        text_id=text_id,
        cbeta_id=meta[0],
        title=meta[1] or "",
        lang=meta[2] or "",
        pali_full=pali_full,
        english_full=english_full,
        pali_chars=len(pali_full) if pali_full else 0,
        english_chars=len(english_full) if english_full else 0,
    )


# === V2: AI difference analysis ===

from app.schemas.ai_diff import AiDiffRequest, AiDiffResponse
from app.services.ai_diff import get_or_create_diff


@router.post("/ai-diff", response_model=AiDiffResponse)
async def ai_diff(
    payload: AiDiffRequest,
    db: AsyncSession = Depends(get_db),
) -> AiDiffResponse:
    """Generate (or fetch cached) cross-canon difference analysis for 2-4 selected chunks."""
    cached, prompt_version, model, analysis = await get_or_create_diff(db, payload.chunks)
    return AiDiffResponse(
        cached=cached,
        prompt_version=prompt_version,
        model=model,
        analysis=analysis,
    )


# ---------------------------------------------------------------------------
# Catalog: which texts have cross-canon alignments at all (discoverability)
# ---------------------------------------------------------------------------

class CatalogEntry(BaseModel):
    """One lzh text's cross-canon alignment coverage, aggregated per language."""
    text_id: int                 # the lzh (Chinese) side
    cbeta_id: str
    title_zh: str
    other_lang: str              # pi / bo / sa
    pair_count: int              # total aligned chunk pairs
    partner_count: int           # distinct counterpart texts (e.g. SC suttas)
    avg_confidence: float
    # Deep-link target: the reader page at the lzh juan with the most
    # anchors. (NOT the /parallel page: 3 of 10 texts have zero anchors at
    # juan 1, and counterpart texts store their whole content as juan 1, so
    # /parallel?juan=N>1 renders a blank partner column.) The reader's
    # per-chunk alignment panel works on any juan that has anchors.
    sample_juan: int
    sample_partner_id: int
    sample_partner_title: str


class AlignmentCatalogResponse(BaseModel):
    entries: list[CatalogEntry]
    total_pairs: int


@router.get("/catalog", response_model=AlignmentCatalogResponse)
async def get_alignment_catalog(db: AsyncSession = Depends(get_db)):
    """All texts with cross-canon alignment coverage, lzh-side normalized.

    alignment_pairs stores direction by pipeline cost (smaller text = text_a),
    so the Chinese text can sit on either side. UNION both orientations into
    (lzh_text, other_lang) rows, then aggregate. Small table (thousands of
    rows), no pagination needed.
    """
    rows = (
        await db.execute(
            sql_text(
                """
                WITH normalized AS (
                    -- NULL-lang rows are deliberately dropped by both
                    -- branches ('!=' is NULL-hostile); langs come from
                    -- buddhist_texts.lang (non-nullable) in practice.
                    SELECT text_a_id AS lzh_id, text_a_juan_num AS lzh_juan,
                           text_b_id AS other_id,
                           text_b_lang AS other_lang, confidence
                    FROM alignment_pairs
                    WHERE text_a_lang = 'lzh' AND text_b_lang != 'lzh'
                          AND text_b_id IS NOT NULL
                    UNION ALL
                    SELECT text_b_id AS lzh_id, text_b_juan_num AS lzh_juan,
                           text_a_id AS other_id,
                           text_a_lang AS other_lang, confidence
                    FROM alignment_pairs
                    WHERE text_b_lang = 'lzh' AND text_a_lang != 'lzh'
                          AND text_a_id IS NOT NULL
                )
                SELECT n.lzh_id,
                       bt.cbeta_id,
                       bt.title_zh,
                       n.other_lang,
                       count(*) AS pair_count,
                       count(DISTINCT n.other_id) AS partner_count,
                       round(avg(n.confidence)::numeric, 2) AS avg_confidence,
                       -- juan with the most anchors = best reader landing
                       mode() WITHIN GROUP (ORDER BY n.lzh_juan) AS sample_juan,
                       -- counterpart with the most pairs (panel shows the rest)
                       mode() WITHIN GROUP (ORDER BY n.other_id) AS sample_partner_id
                FROM normalized n
                JOIN buddhist_texts bt ON bt.id = n.lzh_id
                GROUP BY n.lzh_id, bt.cbeta_id, bt.title_zh, n.other_lang
                ORDER BY pair_count DESC
                """
            )
        )
    ).fetchall()

    partner_ids = {r[8] for r in rows}
    partner_titles: dict[int, str] = {}
    if partner_ids:
        for pid, title in (
            await db.execute(
                sql_text(
                    "SELECT id, COALESCE(NULLIF(title_zh, ''), title_en, cbeta_id) "
                    "FROM buddhist_texts WHERE id = ANY(:ids)"
                ),
                {"ids": list(partner_ids)},
            )
        ).fetchall():
            partner_titles[pid] = title or ""

    entries = [
        CatalogEntry(
            text_id=r[0],
            cbeta_id=r[1] or "",
            title_zh=r[2] or "",
            other_lang=r[3] or "",
            pair_count=r[4],
            partner_count=r[5],
            avg_confidence=float(r[6] or 0),
            sample_juan=r[7] or 1,
            sample_partner_id=r[8],
            sample_partner_title=partner_titles.get(r[8], ""),
        )
        for r in rows
    ]
    return AlignmentCatalogResponse(
        entries=entries,
        total_pairs=sum(e.pair_count for e in entries),
    )
