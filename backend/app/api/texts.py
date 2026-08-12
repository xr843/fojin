import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user
from app.core.exceptions import TextNotFoundError
from app.database import get_db
from app.models.source import DataSource
from app.models.text import BuddhistText
from app.models.user import ReadingHistory, User
from app.schemas.text import JuanContentResponse, JuanLanguagesResponse, JuanListResponse, TextResponseBase
from app.services.audio import get_juan_audio
from app.services.content import (
    get_juan_apparatus,
    get_juan_content,
    get_juan_languages,
    get_juan_line_anchors,
    get_juan_list,
)
from app.services.text import get_text_by_id, get_text_count, get_text_id_by_cbeta
from app.services.text_export import FORMATS as EXPORT_FORMATS
from app.services.text_export import build_export_doc, render

router = APIRouter(tags=["texts"])

# CBETA-style identifier: prefix letter (T/X/J/B/P/C) + 1-4 digits + optional lowercase suffix.
# 例：T0278、X0235a、J1510b。Web search 直跳走这个正则即可。
_CBETA_ID_RE = re.compile(r"^[TXJBPC]\d{1,4}[a-z]?$")


@router.get("/texts/lookup-cbeta")
async def lookup_cbeta_ids(
    ids: str = Query(..., description="Comma-separated CBETA IDs"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Batch lookup CBETA IDs to internal text IDs. Returns {cbeta_id: text_id} for found entries.

    批量将 CBETA 编号映射到系统内部 ID。"""
    cbeta_ids = [s.strip() for s in ids.split(",") if s.strip()][:500]
    if not cbeta_ids:
        return {}
    result = await db.execute(
        select(BuddhistText.cbeta_id, BuddhistText.id).where(BuddhistText.cbeta_id.in_(cbeta_ids))
    )
    return dict(result.all())


class CbetaRedirectResponse(BaseModel):
    text_id: int
    cbeta_id: str
    redirect_to: str


@router.get("/cbeta/{cbeta_id}", response_model=CbetaRedirectResponse)
async def resolve_cbeta_id(
    cbeta_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Resolve a CBETA ID (e.g. ``T0278``) to the canonical ``/texts/{id}`` URL.

    用户在搜索栏输入 CBETA 编号时直跳经文页，跳过结果列表。"""
    cbeta_id = cbeta_id.strip().upper()
    if not _CBETA_ID_RE.match(cbeta_id):
        raise HTTPException(status_code=404, detail="Invalid CBETA ID format")
    text_id = await get_text_id_by_cbeta(db, cbeta_id)
    if text_id is None:
        raise HTTPException(status_code=404, detail=f"CBETA ID {cbeta_id} not found")
    return CbetaRedirectResponse(
        text_id=text_id,
        cbeta_id=cbeta_id,
        redirect_to=f"/texts/{text_id}",
    )


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


class ApparatusReadingItem(BaseModel):
    reading: str
    witnesses: list[str] = []
    resp: str | None = None
    is_omission: bool = False


class ApparatusEntryItem(BaseModel):
    char_start: int
    char_end: int
    lemma: str
    lemma_siglum: str | None = None
    readings: list[ApparatusReadingItem] = []


class JuanApparatusResponse(BaseModel):
    text_id: int
    juan_num: int
    entries: list[ApparatusEntryItem] = []


class LineAnchorItem(BaseModel):
    char_offset: int
    line_ref: str


class JuanLineAnchorsResponse(BaseModel):
    text_id: int
    juan_num: int
    anchors: list[LineAnchorItem] = []


class AudioCueItem(BaseModel):
    char_start: int
    char_end: int
    time_ms: int
    # "head" 经名 / "byline" 译者署名 / "juan" 卷题 / "prose" 正文
    kind: str = "prose"


class TextAudioResponse(BaseModel):
    text_id: int
    juan_num: int
    url: str
    voice_id: str
    engine: str
    duration_ms: int
    cues: list[AudioCueItem] = []


class ChunkContextItem(BaseModel):
    chunk_index: int
    chunk_text: str
    is_center: bool


class ChunkContextResponse(BaseModel):
    text_id: int
    juan_num: int
    title_zh: str
    center_chunk_index: int
    radius: int
    chunks: list[ChunkContextItem]
    has_more_before: bool
    has_more_after: bool


@router.get("/texts/{text_id}", response_model=TextResponseBase)
async def get_text(text_id: int, db: AsyncSession = Depends(get_db)):
    """Get text metadata by ID, including title, translator, dynasty, and source.

    获取经典详情（标题、译者、朝代、数据源等元数据）。"""
    text = await get_text_by_id(db, text_id)
    if not text:
        raise TextNotFoundError(text_id=text_id)
    from app.services.goryeo import goryeo_k, kabc_url
    from app.services.text import canon_from_cbeta_id, canon_label_zh

    response = TextResponseBase.model_validate(text)
    response.canon = canon_from_cbeta_id(text.cbeta_id)
    response.canon_label = canon_label_zh(response.canon)
    response.goryeo_k = goryeo_k(text.cbeta_id)
    response.kabc_url = kabc_url(text.cbeta_id)
    return response


@router.get("/texts/{text_id}/juans", response_model=JuanListResponse)
async def list_juans(text_id: int, db: AsyncSession = Depends(get_db)):
    """List all juan (scrolls/fascicles) of a text.

    获取经典的卷列表。"""
    result = await get_juan_list(db, text_id)
    if result is None:
        raise TextNotFoundError(text_id=text_id)
    return result


@router.get("/texts/{text_id}/juans/{juan_num}/languages", response_model=JuanLanguagesResponse)
async def juan_languages(text_id: int, juan_num: int, db: AsyncSession = Depends(get_db)):
    """Get available language versions for a specific juan.

    获取某卷的可用语言列表。"""
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
    """Read the content of a specific juan. Reading history is recorded for authenticated users.

    获取经典某一卷的内容。登录用户自动记录阅读历史。"""
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


@router.get("/texts/{text_id}/juans/{juan_num}/apparatus", response_model=JuanApparatusResponse)
async def read_juan_apparatus(
    text_id: int,
    juan_num: int,
    db: AsyncSession = Depends(get_db),
):
    """Critical apparatus (校勘异文) for a juan: variant readings of the base
    text (底本) against witness canons (宋/元/明…), positioned by char offset.

    获取某一卷的校勘异文（底本与宋元明等校本的异读），按字符位置标注。
    Loaded lazily by the reader — a major text can carry thousands of entries."""
    entries = await get_juan_apparatus(db, text_id, juan_num)
    return JuanApparatusResponse(text_id=text_id, juan_num=juan_num, entries=entries)


@router.get("/texts/{text_id}/juans/{juan_num}/line-anchors", response_model=JuanLineAnchorsResponse)
async def read_juan_line_anchors(
    text_id: int,
    juan_num: int,
    db: AsyncSession = Depends(get_db),
):
    """CBETA <lb> page-column-line anchors for a juan (char_offset → line_ref).

    获取某一卷的页·栏·行锚点，供阅读器按需定位引用与 URN 跳行。
    Loaded lazily by the reader; a juan can carry several hundred anchors."""
    anchors = await get_juan_line_anchors(db, text_id, juan_num)
    return JuanLineAnchorsResponse(text_id=text_id, juan_num=juan_num, anchors=anchors)


@router.get("/texts/{text_id}/juans/{juan_num}/audio", response_model=TextAudioResponse)
async def read_juan_audio(
    text_id: int,
    juan_num: int,
    lang: str = Query("zh", description="正文语言"),
    db: AsyncSession = Depends(get_db),
):
    """某一卷的读诵音频与句级时间戳。

    获取某一卷的在线读诵音频。音频文件本身由静态目录直出（一部经 1~17 MB，
    走后端是纯浪费），此处只回地址与时间戳；**没有音频的卷返回 404**，
    前端据此不渲染「读诵」按钮。"""
    payload = await get_juan_audio(db, text_id, juan_num, lang)
    if payload is None:
        raise HTTPException(status_code=404, detail="该卷暂无读诵音频")
    return TextAudioResponse(text_id=text_id, juan_num=juan_num, **payload)


@router.get("/texts/{text_id}/export", tags=["exports"])
async def export_text(
    text_id: int,
    format: str = Query("txt", description="导出格式：txt / html / docx / epub"),
    juan: int | None = Query(None, description="仅导出该卷；省略则导出全经"),
    db: AsyncSession = Depends(get_db),
):
    """Export one sutra as a downloadable document (TXT / HTML / DOCX / EPUB).

    将单部经典导出为可下载文档（纯文本 / 网页 / Word / EPUB 电子书）。
    ``juan`` 省略时导出全经，否则仅导出该卷。"""
    if format not in EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"unsupported format: {format}")
    doc = await build_export_doc(db, text_id, juan)
    if doc is None:
        raise TextNotFoundError(text_id=text_id)
    payload, media_type = render(doc, format)
    ext, _ = EXPORT_FORMATS[format]
    suffix = f"_juan{juan}" if juan is not None else ""
    filename = f"{doc.cbeta_id}{suffix}{ext}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """Get platform-wide statistics (total text count + active source count).

    获取平台统计数据。"""
    count = await get_text_count(db)
    source_count = (
        await db.execute(
            select(func.count(DataSource.id)).where(DataSource.is_active.is_(True))
        )
    ).scalar() or 0
    return {"total_texts": count, "source_count": int(source_count)}


@router.get("/texts/{text_id}/juans/{juan_num}/similar", response_model=SimilarPassagesResponse)
async def similar_passages(
    text_id: int,
    juan_num: int,
    limit: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """Find semantically similar passages in other texts using pgvector embeddings.

    基于 pgvector 语义相似度，查找其他经典中的相似段落。"""
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


@router.get(
    "/texts/{text_id}/juans/{juan_num}/chunks/{chunk_index}/context",
    response_model=ChunkContextResponse,
)
async def get_chunk_context(
    text_id: int,
    juan_num: int,
    chunk_index: int,
    radius: int = Query(2, ge=0, le=5),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a cited chunk plus ``radius`` adjacent chunks from the same juan.

    Powers the in-chat citation drawer so users can verify an AI answer
    against the original passage without leaving the conversation. The
    response is pure data — the frontend handles the 50-char overlap
    dedup when it stitches chunks for display.

    取得指定 chunk 及其前后 radius 个同卷相邻 chunk，用于 AI 回答引文的
    即时原文对照侧栏。"""
    raw_conn = await db.connection()

    # Title lookup — single row
    title_row = (
        await raw_conn.exec_driver_sql(
            "SELECT COALESCE(title_zh, '') FROM buddhist_texts WHERE id = $1",
            (text_id,),
        )
    ).fetchone()
    if title_row is None:
        raise TextNotFoundError(text_id=text_id)
    title_zh = title_row[0]

    low = max(chunk_index - radius, 0)
    high = chunk_index + radius

    chunk_rows = (
        await raw_conn.exec_driver_sql(
            "SELECT chunk_index, chunk_text FROM text_embeddings "
            "WHERE text_id = $1 AND juan_num = $2 "
            "AND chunk_index BETWEEN $3 AND $4 "
            "ORDER BY chunk_index",
            (text_id, juan_num, low, high),
        )
    ).fetchall()

    chunks = [
        ChunkContextItem(
            chunk_index=row[0],
            chunk_text=row[1],
            is_center=(row[0] == chunk_index),
        )
        for row in chunk_rows
    ]

    # Boundary detection — both directions need a real existence probe.
    #
    # `has_more_before = low > 0` used to be an arithmetic shortcut, justified by
    # "chunks within a juan are contiguous (0..max)". That premise only holds when
    # the requested chunk itself exists. When it does not — unknown juan_num, a
    # chunk_index past the end, or a text with no embeddings — the query above
    # returns nothing, yet the shortcut still claimed "there is more before" for
    # any chunk_index > radius. The drawer then rendered the 「前文（本卷第 N 段之前）」
    # hint above a blank body, telling the reader content exists where none does.
    # A citation you cannot open is worse than no citation, so this now asks the
    # database instead of asserting.
    before_probe = (
        await raw_conn.exec_driver_sql(
            "SELECT 1 FROM text_embeddings "
            "WHERE text_id = $1 AND juan_num = $2 AND chunk_index < $3 "
            "LIMIT 1",
            (text_id, juan_num, low),
        )
    ).fetchone()
    has_more_before = before_probe is not None
    after_probe = (
        await raw_conn.exec_driver_sql(
            "SELECT 1 FROM text_embeddings "
            "WHERE text_id = $1 AND juan_num = $2 AND chunk_index > $3 "
            "LIMIT 1",
            (text_id, juan_num, high),
        )
    ).fetchone()
    has_more_after = after_probe is not None

    return ChunkContextResponse(
        text_id=text_id,
        juan_num=juan_num,
        title_zh=title_zh,
        center_chunk_index=chunk_index,
        radius=radius,
        chunks=chunks,
        has_more_before=has_more_before,
        has_more_after=has_more_after,
    )


# ── Version aggregation (IIIF + cross-source) ──────────────────────


class VersionTranslation(BaseModel):
    text_id: int
    title_zh: str | None = None
    title_en: str | None = None
    translator: str | None = None
    dynasty: str | None = None
    lang: str | None = None
    source_name: str | None = None
    relation_type: str | None = None


class VersionIIIF(BaseModel):
    id: int
    label: str | None = None
    manifest_url: str
    thumbnail_url: str | None = None
    provider: str | None = None


class VersionSourceLink(BaseModel):
    source_name: str
    source_url: str | None = None


class TextVersionsResponse(BaseModel):
    text_id: int
    title_zh: str | None = None
    translations: list[VersionTranslation]
    iiif_manifests: list[VersionIIIF]
    source_links: list[VersionSourceLink]


@router.get("/texts/{text_id}/versions", response_model=TextVersionsResponse)
async def get_text_versions(text_id: int, db: AsyncSession = Depends(get_db)):
    """Get all versions of a text: translations, parallel texts, IIIF manifests, and source links.

    获取经典的所有版本：不同译本、平行文本、IIIF写本图像、各数据源链接。"""
    text = await get_text_by_id(db, text_id)
    if not text:
        raise TextNotFoundError(text_id=text_id)

    raw = await db.connection()

    # 1. Related translations and parallel texts
    tr_rows = await raw.exec_driver_sql(
        "SELECT bt.id, bt.title_zh, bt.title_en, bt.translator, bt.dynasty, bt.lang, "
        "ds.name_zh as source_name, tr.relation_type "
        "FROM text_relations tr "
        "JOIN buddhist_texts bt ON bt.id = (CASE WHEN tr.text_a_id = $1 THEN tr.text_b_id ELSE tr.text_a_id END) "
        "LEFT JOIN data_sources ds ON bt.source_id = ds.id "
        "WHERE (tr.text_a_id = $1 OR tr.text_b_id = $1) "
        "ORDER BY tr.relation_type, bt.lang, bt.dynasty",
        (text_id,),
    )
    tr_rows_data = list(tr_rows.fetchall())

    # Also find same-title texts (different translations of same sutra)
    title_rows = await raw.exec_driver_sql(
        "SELECT bt.id, bt.title_zh, bt.title_en, bt.translator, bt.dynasty, bt.lang, "
        "ds.name_zh as source_name, NULL as relation_type "
        "FROM buddhist_texts bt "
        "LEFT JOIN data_sources ds ON bt.source_id = ds.id "
        "WHERE bt.title_zh = (SELECT title_zh FROM buddhist_texts WHERE id = $1) "
        "AND bt.id != $1 "
        "ORDER BY bt.dynasty, bt.translator",
        (text_id,),
    )
    existing_ids = {r[0] for r in tr_rows_data}
    for r in title_rows.fetchall():
        if r[0] not in existing_ids:
            tr_rows_data.append(r)

    # Deduplicate by translator: same translator = same translation, keep first
    # Also skip entries whose translator matches the current text's translator
    seen_translators: set[str] = set()
    current_translator = (text.translator or "").strip()
    if current_translator:
        seen_translators.add(current_translator)
    deduped: list = []
    for r in tr_rows_data:
        translator = (r[3] or "").strip()
        # Normalize: "魏 菩提流支" and "菩提流支" are the same
        norm_translator = translator.split()[-1] if translator else ""
        if norm_translator and norm_translator in seen_translators:
            continue
        if norm_translator:
            seen_translators.add(norm_translator)
        deduped.append(r)

    translations = [
        VersionTranslation(
            text_id=r[0], title_zh=r[1], title_en=r[2],
            translator=r[3], dynasty=r[4], lang=r[5],
            source_name=r[6], relation_type=r[7],
        )
        for r in deduped
    ]

    # 2. IIIF manifests
    iiif_rows = await raw.exec_driver_sql(
        """SELECT id, label, manifest_url, thumbnail_url, provider
           FROM iiif_manifests WHERE text_id = $1
           ORDER BY provider""",
        (text_id,),
    )
    iiif = [
        VersionIIIF(id=r[0], label=r[1], manifest_url=r[2], thumbnail_url=r[3], provider=r[4])
        for r in iiif_rows.fetchall()
    ]

    # 3. Source links (where this text can be read)
    link_rows = await raw.exec_driver_sql(
        """SELECT ds.name_zh, ti.source_url
           FROM text_identifiers ti
           JOIN data_sources ds ON ti.source_id = ds.id
           WHERE ti.text_id = $1
           ORDER BY ds.sort_order""",
        (text_id,),
    )
    links = [
        VersionSourceLink(source_name=r[0], source_url=r[1])
        for r in link_rows.fetchall()
    ]

    return TextVersionsResponse(
        text_id=text_id,
        title_zh=text.title_zh,
        translations=translations,
        iiif_manifests=iiif,
        source_links=links,
    )
