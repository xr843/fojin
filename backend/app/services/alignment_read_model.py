"""Unified read model over FoJin's three disjoint alignment stores.

The platform accumulated three alignment stores with incompatible shapes:

* ``alignment_pairs`` — chunk-level fojin↔fojin pairs (0010 + 0120 + 0168),
  referenced positionally via (text_id, juan_num, chunk_index) on both sides,
  with an LLM/reviewer ``confidence`` and a ``method`` provenance column.
* ``mitra_alignments`` — ~896K sentence-level rows (0156): Chinese side
  anchored to a fojin chunk, foreign side INLINE (foreign_text/foreign_lang,
  no fojin counterpart). Its ``confidence`` is a constant 1.0 import flag,
  NOT a quality score.
* ``text_relations`` (source='suttacentral') — sutta-level (whole-text)
  Akanuma-style parallels (0005), no numeric confidence at all.

This service merges them behind one normalized record (:class:`ParallelRecord`)
so callers stop re-implementing the merge and — critically — stop comparing
incomparable "confidence" numbers: every record carries a ``confidence_kind``
(``llm`` / ``import_flag`` / ``catalog``) alongside the raw value.

SQL stays set-based (constant query count per call, no N+1), preserving the
direction-agnostic CASE handling from the original api/alignment.py handlers.
RAG integration is deliberately out of scope for this phase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import bindparam
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

Granularity = Literal["sutta", "chunk"]
ConfidenceKind = Literal["llm", "import_flag", "catalog"]

# A fojin chunk (paragraph) can contain many MITRA sentence-level parallels;
# cap per chunk so reader panels / callers stay bounded on dense texts.
MITRA_CHUNK_LIMIT = 50

# alignment_pairs.method values written by the known producers. Rows created
# before 0120 have method NULL; chunk-level rows should always carry one, but
# a NULL is normalized to "embed_llm" (the bulk producer) rather than crashing.
_KNOWN_PAIR_METHODS = ("embed_llm", "manual", "expert", "heuristic", "flywheel-verified")
_DEFAULT_PAIR_METHOD = "embed_llm"


@dataclass(frozen=True, slots=True)
class SegmentRef:
    """One side of an alignment.

    ``text_id`` is None for MITRA's inline foreign side (no fojin text row —
    the sentence lives only in ``ParallelRecord.preview``). ``juan_num`` and
    ``chunk_index`` are None for sutta-level (whole-text) records.
    ``char_start``/``char_end`` are offsets into the (text_id, juan_num, lang)
    row of text_contents — the re-chunking-stable anchor from migration 0168 —
    and are None until backfilled.
    """

    text_id: int | None = None
    juan_num: int | None = None
    chunk_index: int | None = None
    lang: str | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True, slots=True)
class SentencePairRecord:
    """One normalized sentence-level parallel from ``sentence_alignments``.

    Phase 4 Package C: a finer-grained companion to :class:`ParallelRecord`,
    kept separate because the sentence store's shape differs (both sides carry a
    verbatim ``sent_text`` substring and sub-paragraph char spans on BOTH sides
    so the reader can highlight the exact aligned run inside each paragraph).

    ``self_ref`` is the requested text's side (``text_id``/``juan_num`` echo the
    query args, ``char_start``/``char_end``/``lang`` are its own offsets);
    ``other_ref`` is the counterpart (its ``text_id``/``juan_num``/offsets/lang).
    ``chunk_index`` is always None — sentence rows anchor on char offsets, not
    positional chunk indices.

    ``similarity`` is the averaged cross-lingual cosine of the aligned
    sentence(s) — a real quality score (unlike MITRA's constant import flag), so
    no ``confidence_kind`` tag is needed. ``align_type`` is the bertalign move
    (``1-1`` / ``1-2`` / ``2-1``), ``method`` the producer, ``is_verified`` the
    reviewer flag.
    """

    self_ref: SegmentRef
    other_ref: SegmentRef
    self_text: str
    other_text: str
    similarity: float
    align_type: str
    method: str
    is_verified: bool
    title: str = ""


@dataclass(frozen=True, slots=True)
class ParallelRecord:
    """One normalized parallel, whichever store it came from.

    ``source`` provenance values:
      embed_llm / manual / expert / heuristic / flywheel-verified —
        alignment_pairs.method (chunk granularity);
      mitra — mitra_alignments (chunk granularity, inline foreign side);
      suttacentral — text_relations (sutta granularity).

    ``confidence`` MUST be read together with ``confidence_kind``:
      llm         — a real quality score from LLM/reviewer verification;
      import_flag — MITRA's constant 1.0: means "passed the import substring
                    gate", NOT comparable with llm scores;
      catalog     — no numeric score; trust derives from the upstream catalog
                    (confidence is None).

    ``preview`` is the display text of the counterpart (counterpart chunk_text
    for fojin pairs — which for pi/bo texts is the English translation —, the
    inline foreign sentence for MITRA, the English preview for sutta records).
    ``original_preview``/``original_lang`` carry a source-language sample
    (Pāli/Sanskrit) when one exists in text_contents.
    """

    granularity: Granularity
    source: str
    confidence: float | None
    confidence_kind: ConfidenceKind | None
    self_ref: SegmentRef
    other_ref: SegmentRef
    preview: str | None = None
    title: str = ""
    original_preview: str | None = None
    original_lang: str | None = None
    # Sutta-level extras (text_relations); None for chunk-level records.
    relation_type: str | None = None
    note: str | None = None
    other_cbeta_id: str | None = None


def _pair_source(method: str | None) -> str:
    """Normalize alignment_pairs.method to a provenance source string."""
    if not method:
        return _DEFAULT_PAIR_METHOD
    if method not in _KNOWN_PAIR_METHODS:
        # Unknown producer: keep it visible rather than mislabeling it.
        logger.debug("alignment_pairs row with unrecognized method %r", method)
    return method


async def get_chunk_parallels(
    session: AsyncSession,
    text_id: int,
    juan_num: int,
    chunk_index: int,
    *,
    limit: int = 5,
) -> list[ParallelRecord]:
    """All chunk-granularity parallels for one fojin chunk, both stores merged.

    Order matches the legacy /alignment/chunks endpoint exactly: fojin pairs
    first (confidence DESC, counterpart identity as tiebreak — confidence is
    coarse and heavily tied, so the tiebreak keeps this endpoint and the
    batched juan endpoint selecting the SAME rows in the SAME order), then
    MITRA rows (foreign_lang, id — capped at MITRA_CHUNK_LIMIT, not `limit`).

    Constant 4 queries max: pairs → counterpart chunks (batched IN) →
    pi/sa previews (batched IN) → mitra.
    """
    pair_rows = (await session.execute(
        sql_text("""
            WITH base AS (
                SELECT ap.*,
                       (ap.text_a_id = :tid AND ap.text_a_juan_num = :juan
                        AND ap.text_a_chunk_index = :cidx) AS a_is_src
                FROM alignment_pairs ap
                WHERE ap.text_a_chunk_index IS NOT NULL
                  AND (
                    (ap.text_a_id = :tid AND ap.text_a_juan_num = :juan AND ap.text_a_chunk_index = :cidx)
                    OR
                    (ap.text_b_id = :tid AND ap.text_b_juan_num = :juan AND ap.text_b_chunk_index = :cidx)
                  )
            )
            SELECT
                CASE WHEN a_is_src THEN text_b_id ELSE text_a_id END AS other_tid,
                CASE WHEN a_is_src THEN text_b_juan_num ELSE text_a_juan_num END AS other_juan,
                CASE WHEN a_is_src THEN text_b_chunk_index ELSE text_a_chunk_index END AS other_cidx,
                CASE WHEN a_is_src THEN text_b_lang ELSE text_a_lang END AS other_lang,
                CASE WHEN a_is_src THEN text_a_lang ELSE text_b_lang END AS self_lang,
                CASE WHEN a_is_src THEN text_a_char_start ELSE text_b_char_start END AS self_char_start,
                CASE WHEN a_is_src THEN text_a_char_end ELSE text_b_char_end END AS self_char_end,
                CASE WHEN a_is_src THEN text_b_char_start ELSE text_a_char_start END AS other_char_start,
                CASE WHEN a_is_src THEN text_b_char_end ELSE text_a_char_end END AS other_char_end,
                confidence, method
            FROM base
            ORDER BY confidence DESC, other_tid, other_juan, other_cidx
            LIMIT :limit
        """),
        {"tid": text_id, "juan": juan_num, "cidx": chunk_index, "limit": limit},
    )).fetchall()

    # Batched counterpart chunk_text + title.
    te_keys = {(r[0], r[1], r[2]) for r in pair_rows}
    te_map: dict[tuple, tuple] = {}
    if te_keys:
        te_rows = (await session.execute(
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
    tc_keys = {(r[0], r[1], r[3]) for r in pair_rows if r[3] in ("pi", "sa")}
    tc_map: dict[tuple, str] = {}
    if tc_keys:
        tc_rows = (await session.execute(
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
                tc_map[(tid_, juan_, lang_)] = preview

    records: list[ParallelRecord] = []
    for row in pair_rows:
        (other_tid, other_juan, other_cidx, other_lang, self_lang,
         self_cs, self_ce, other_cs, other_ce, conf, method) = row
        te = te_map.get((other_tid, other_juan, other_cidx))
        if not te:
            # Counterpart chunk no longer exists (stale positional ref) —
            # same skip the legacy endpoint applied.
            continue
        ctext, title = te
        original_preview = tc_map.get((other_tid, other_juan, other_lang))
        records.append(ParallelRecord(
            granularity="chunk",
            source=_pair_source(method),
            confidence=float(conf) if conf is not None else None,
            confidence_kind="llm",
            self_ref=SegmentRef(
                text_id=text_id, juan_num=juan_num, chunk_index=chunk_index,
                lang=self_lang, char_start=self_cs, char_end=self_ce,
            ),
            other_ref=SegmentRef(
                text_id=other_tid, juan_num=other_juan, chunk_index=other_cidx,
                lang=other_lang, char_start=other_cs, char_end=other_ce,
            ),
            preview=ctext,
            title=title or "",
            original_preview=original_preview,
            original_lang=other_lang if original_preview else None,
        ))

    # MITRA cross-lingual parallels (inline Sanskrit/Tibetan, CC BY-SA 4.0).
    mitra_rows = (await session.execute(
        sql_text(
            "SELECT foreign_text, foreign_lang, confidence "
            "FROM mitra_alignments "
            "WHERE text_id = :tid AND juan_num = :juan AND chunk_index = :cidx "
            "ORDER BY foreign_lang, id LIMIT :limit"
        ),
        {"tid": text_id, "juan": juan_num, "cidx": chunk_index, "limit": MITRA_CHUNK_LIMIT},
    )).fetchall()
    for foreign_text, foreign_lang, conf in mitra_rows:
        records.append(ParallelRecord(
            granularity="chunk",
            source="mitra",
            # Constant 1.0 import flag — kept, but tagged import_flag so no
            # caller can mistake it for a comparable quality score.
            confidence=float(conf) if conf is not None else 1.0,
            confidence_kind="import_flag",
            self_ref=SegmentRef(
                text_id=text_id, juan_num=juan_num, chunk_index=chunk_index, lang="lzh",
            ),
            other_ref=SegmentRef(text_id=None, lang=foreign_lang or "sa"),
            preview=foreign_text,
        ))

    return records


async def get_text_parallels(
    session: AsyncSession,
    text_id: int,
) -> list[ParallelRecord]:
    """Sutta-level (whole-text) parallels for one text, from text_relations.

    Ports the /alignment/canonical merge set-based: relations → counterpart
    metadata (batched) → Pāli previews (batched) → English previews (batched);
    constant 4 queries max instead of the legacy 1 + 3·N. Direction-agnostic
    via the same CASE as the legacy handler; ordering matches it too
    (parallel-type first, then cbeta_id).
    """
    rel_rows = (await session.execute(
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
    if not rel_rows:
        return []

    rel_ids = sorted({r[0] for r in rel_rows})
    meta_map: dict[int, tuple] = {}  # rel_id -> (cbeta_id, title, lang)
    meta_rows = (await session.execute(
        sql_text(
            "SELECT id, cbeta_id, "
            "COALESCE(title_pi, title_sa, title_en, title_zh, '') AS title, lang "
            "FROM buddhist_texts WHERE id = ANY(:ids)"
        ),
        {"ids": rel_ids},
    )).fetchall()
    for rid, cbeta, title, lang in meta_rows:
        meta_map[rid] = (cbeta, title, lang)

    # Previews only exist for pi counterparts (legacy behavior): Pāli source
    # sample from text_contents, English sample from the first chunk.
    pi_ids = sorted(rid for rid, m in meta_map.items() if m[2] == "pi")
    pali_map: dict[int, str] = {}
    en_map: dict[int, str] = {}
    if pi_ids:
        pali_rows = (await session.execute(
            sql_text("""
                SELECT DISTINCT ON (text_id) text_id, LEFT(content, 240)
                FROM text_contents
                WHERE text_id = ANY(:ids) AND lang = 'pi'
                ORDER BY text_id, juan_num
            """),
            {"ids": pi_ids},
        )).fetchall()
        pali_map = {tid: preview for tid, preview in pali_rows if preview}
        en_rows = (await session.execute(
            sql_text("""
                SELECT DISTINCT ON (text_id) text_id, LEFT(chunk_text, 240)
                FROM text_embeddings
                WHERE text_id = ANY(:ids)
                ORDER BY text_id, juan_num, chunk_index
            """),
            {"ids": pi_ids},
        )).fetchall()
        en_map = {tid: preview for tid, preview in en_rows if preview}

    records: list[ParallelRecord] = []
    for rel_id, rel_type, note in rel_rows:
        meta = meta_map.get(rel_id)
        if not meta:
            continue
        cbeta, title, lang = meta
        pali_preview = pali_map.get(rel_id)
        records.append(ParallelRecord(
            granularity="sutta",
            source="suttacentral",
            confidence=None,
            confidence_kind="catalog",
            self_ref=SegmentRef(text_id=text_id),
            other_ref=SegmentRef(text_id=rel_id, lang=lang),
            preview=en_map.get(rel_id),
            title=title or "",
            original_preview=pali_preview,
            original_lang="pi" if pali_preview else None,
            relation_type=rel_type,
            note=note,
            other_cbeta_id=cbeta,
        ))

    records.sort(key=lambda r: (0 if r.relation_type == "parallel" else 1, r.other_cbeta_id or ""))
    return records


async def get_sentence_parallels(
    session: AsyncSession,
    text_id: int,
    juan_num: int,
    *,
    limit: int = 200,
) -> list[SentencePairRecord]:
    """All sentence-level parallels for one (text_id, juan_num), both directions.

    Reads ``sentence_alignments`` direction-agnostically: the requested text may
    sit on side A or side B of any given row, so a single CASE (mirroring
    :func:`get_chunk_parallels`) folds each match to "self" (the requested side)
    vs "other" (the counterpart), and ``buddhist_texts`` is LEFT JOINed on the
    resolved counterpart id for its display title. One set-based query, no N+1.

    Rows come back in reading order — the self side's ``char_start`` ascending —
    with ``similarity`` DESC as the tiebreak so the strongest alignment wins when
    two rows share a leading offset. ``char_start``/``char_end`` are carried on
    BOTH sides so the reader can highlight the exact sub-paragraph spans.

    Returns ``[]`` when the table has no rows for this juan (the dark state the
    read endpoint serves until ``refine_sentence_alignments.py`` backfills).
    """
    rows = (await session.execute(
        sql_text("""
            WITH base AS (
                SELECT sa.*,
                       (sa.text_a_id = :tid AND sa.text_a_juan_num = :juan) AS a_is_src
                FROM sentence_alignments sa
                WHERE (sa.text_a_id = :tid AND sa.text_a_juan_num = :juan)
                   OR (sa.text_b_id = :tid AND sa.text_b_juan_num = :juan)
            ),
            resolved AS (
                SELECT
                    CASE WHEN a_is_src THEN text_a_char_start ELSE text_b_char_start END AS self_cs,
                    CASE WHEN a_is_src THEN text_a_char_end   ELSE text_b_char_end   END AS self_ce,
                    CASE WHEN a_is_src THEN text_a_lang       ELSE text_b_lang       END AS self_lang,
                    CASE WHEN a_is_src THEN sent_a_text       ELSE sent_b_text       END AS self_text,
                    CASE WHEN a_is_src THEN text_b_id         ELSE text_a_id         END AS other_tid,
                    CASE WHEN a_is_src THEN text_b_juan_num   ELSE text_a_juan_num   END AS other_juan,
                    CASE WHEN a_is_src THEN text_b_char_start ELSE text_a_char_start END AS other_cs,
                    CASE WHEN a_is_src THEN text_b_char_end   ELSE text_a_char_end   END AS other_ce,
                    CASE WHEN a_is_src THEN text_b_lang       ELSE text_a_lang       END AS other_lang,
                    CASE WHEN a_is_src THEN sent_b_text       ELSE sent_a_text       END AS other_text,
                    similarity, align_type, method, is_verified
                FROM base
            )
            SELECT
                r.self_cs, r.self_ce, r.self_lang, r.self_text,
                r.other_tid, r.other_juan, r.other_cs, r.other_ce, r.other_lang, r.other_text,
                r.similarity, r.align_type, r.method, r.is_verified,
                COALESCE(bt.title_zh, bt.title_sa, bt.title_pi, bt.title_en, '') AS other_title
            FROM resolved r
            LEFT JOIN buddhist_texts bt ON bt.id = r.other_tid
            ORDER BY r.self_cs, r.similarity DESC
            LIMIT :limit
        """),
        {"tid": text_id, "juan": juan_num, "limit": limit},
    )).fetchall()

    records: list[SentencePairRecord] = []
    for row in rows:
        (self_cs, self_ce, self_lang, self_text,
         other_tid, other_juan, other_cs, other_ce, other_lang, other_text,
         similarity, align_type, method, is_verified, other_title) = row
        records.append(SentencePairRecord(
            self_ref=SegmentRef(
                text_id=text_id, juan_num=juan_num,
                lang=self_lang, char_start=self_cs, char_end=self_ce,
            ),
            other_ref=SegmentRef(
                text_id=other_tid, juan_num=other_juan,
                lang=other_lang, char_start=other_cs, char_end=other_ce,
            ),
            self_text=self_text or "",
            other_text=other_text or "",
            similarity=float(similarity) if similarity is not None else 0.0,
            align_type=align_type or "",
            method=method or "",
            is_verified=bool(is_verified),
            title=other_title or "",
        ))
    return records
