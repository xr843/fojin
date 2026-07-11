"""Shared logic for publishing FoJin's cross-canon alignment dataset.

Both the CLI exporter (``scripts/export_alignment_dataset.py``) and the HTTP
endpoint (``GET /exports/alignments.jsonl``) build the *same* JSONL from this
module so the SQL and the record/card shapes never drift apart.

Two granularities:

* ``chunk`` — ``alignment_pairs`` rows (chunk-level Pāli/Chinese/Tibetan
  parallels), the segment text pulled from ``text_embeddings.chunk_text``.
* ``sentence`` — ``sentence_alignments`` rows (finer bertalign refinement).
  The table is empty until a prod job runs; this mode still produces a valid
  card (``record_count: 0``) and a body with zero record lines.

Every record carries a per-side ``license`` + ``attribution`` sourced from the
side's ``data_sources`` row (via ``buddhist_texts.source_id``) so downstream
consumers know each segment's license. The dataset **card** — emitted as the
first JSONL line — aggregates the *distinct* per-source licenses actually
present in the exported rows, so it truthfully reflects the included sources.

Design notes:

* Read-only. Every statement is a ``SELECT``.
* Streaming. Records are pulled with keyset pagination (``id > :last_id``) in
  ``DEFAULT_BATCH`` chunks — the table can be large, so we never materialize the
  whole result set. Card facts (count + distinct licenses) are computed with
  small server-side aggregate queries, not by buffering rows.
* Each batch runs in its own short-lived session (mirrors ``api/exports.py``'s
  ``_fetch_batch``) so a slow client streaming the download never pins a pooled
  connection for the whole response.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterable, Sequence

from sqlalchemy import bindparam, text

from app.database import async_session

# ---------------------------------------------------------------------------
# Dataset identity / license constants
# ---------------------------------------------------------------------------

DATASET_NAME = "fojin-cross-canon-alignments"
DEFAULT_VERSION = "0.1.0"
# The alignment *annotations* (FoJin's own contribution) ship under CC BY-SA
# 4.0. The quoted segment text keeps each upstream source's own license — see
# ``source_licenses`` in the card and ``provenance_note`` below.
DATASET_LICENSE = "CC-BY-SA-4.0"

PROVENANCE_NOTE = (
    "Alignment annotations (segment pairings, confidence/similarity, method, "
    "verification flag) are FoJin's own contribution and are released under "
    "CC BY-SA 4.0. The quoted segment text belongs to the upstream canonical "
    "sources listed in `source_licenses` and remains under each source's own "
    "license; redistribution must preserve every source's attribution and "
    "license terms. Sources under a NonCommercial license (e.g. CBETA "
    "CC BY-NC-SA 4.0) cap the combined dataset to non-commercial reuse — see "
    "backend/docs/mitra-license.md for the ShareAlike x NC analysis."
)

_CITATION_TEMPLATE = (
    "FoJin (佛津) Cross-Canon Alignment Dataset v{version}. "
    "FoJin Buddhist Digital Text Platform, https://fojin.org. "
    "Alignment annotations licensed CC BY-SA 4.0."
)

DEFAULT_BATCH = 500

# Session factory type: a zero-arg callable returning an async-context-manager
# session (``async_session`` in prod; a fake in tests).
SessionFactory = Callable[[], object]


# ---------------------------------------------------------------------------
# SQL fragments
# ---------------------------------------------------------------------------

# Chunk mode. LEFT JOIN data_sources so a text whose source_id is NULL (the FK
# is ON DELETE SET NULL) keeps its row — additive license columns must never
# drop a previously-exported pair (backward compatibility).
_CHUNK_FROM = """
FROM alignment_pairs p
JOIN buddhist_texts ta ON ta.id = p.text_a_id
JOIN buddhist_texts tb ON tb.id = p.text_b_id
LEFT JOIN data_sources sa ON sa.id = ta.source_id
LEFT JOIN data_sources sb ON sb.id = tb.source_id
JOIN text_embeddings ea
  ON ea.text_id = p.text_a_id
 AND ea.juan_num = p.text_a_juan_num
 AND ea.chunk_index = p.text_a_chunk_index
JOIN text_embeddings eb
  ON eb.text_id = p.text_b_id
 AND eb.juan_num = p.text_b_juan_num
 AND eb.chunk_index = p.text_b_chunk_index
"""

_CHUNK_COLUMNS = """
    p.id,
    p.text_a_lang           AS lang_src,
    p.text_b_lang           AS lang_tgt,
    p.text_a_id             AS src_text_id,
    ta.cbeta_id             AS src_canonical_id,
    ta.title_zh             AS src_title,
    p.text_a_juan_num       AS src_juan,
    p.text_a_chunk_index    AS src_chunk,
    sa.license_spdx         AS src_license_spdx,
    sa.license_url          AS src_license_url,
    sa.name_zh              AS src_source_name_zh,
    sa.name_en              AS src_source_name_en,
    sa.attribution_required AS src_attr_required,
    p.text_b_id             AS tgt_text_id,
    tb.cbeta_id             AS tgt_canonical_id,
    tb.title_zh             AS tgt_title,
    p.text_b_juan_num       AS tgt_juan,
    p.text_b_chunk_index    AS tgt_chunk,
    sb.license_spdx         AS tgt_license_spdx,
    sb.license_url          AS tgt_license_url,
    sb.name_zh              AS tgt_source_name_zh,
    sb.name_en              AS tgt_source_name_en,
    sb.attribution_required AS tgt_attr_required,
    ea.chunk_text           AS segment_src,
    eb.chunk_text           AS segment_tgt,
    p.confidence,
    p.method,
    p.is_verified
"""

# Sentence mode (sentence_alignments, migration 0170).
_SENTENCE_FROM = """
FROM sentence_alignments s
JOIN buddhist_texts ta ON ta.id = s.text_a_id
JOIN buddhist_texts tb ON tb.id = s.text_b_id
LEFT JOIN data_sources sa ON sa.id = ta.source_id
LEFT JOIN data_sources sb ON sb.id = tb.source_id
"""

_SENTENCE_COLUMNS = """
    s.id,
    s.align_type,
    s.similarity,
    s.method,
    s.text_a_id             AS src_text_id,
    ta.title_zh             AS src_title,
    s.text_a_juan_num       AS src_juan,
    s.text_a_char_start     AS src_char_start,
    s.text_a_char_end       AS src_char_end,
    s.text_a_lang           AS src_lang,
    s.sent_a_text           AS src_text,
    sa.license_spdx         AS src_license_spdx,
    sa.license_url          AS src_license_url,
    sa.name_zh              AS src_source_name_zh,
    sa.name_en              AS src_source_name_en,
    sa.attribution_required AS src_attr_required,
    s.text_b_id             AS tgt_text_id,
    tb.title_zh             AS tgt_title,
    s.text_b_juan_num       AS tgt_juan,
    s.text_b_char_start     AS tgt_char_start,
    s.text_b_char_end       AS tgt_char_end,
    s.text_b_lang           AS tgt_lang,
    s.sent_b_text           AS tgt_text,
    sb.license_spdx         AS tgt_license_spdx,
    sb.license_url          AS tgt_license_url,
    sb.name_zh              AS tgt_source_name_zh,
    sb.name_en              AS tgt_source_name_en,
    sb.attribution_required AS tgt_attr_required
"""


def _config(granularity: str) -> dict:
    """Per-granularity SQL bits: FROM clause, column list, and the column names
    of the score / id / lang-a / lang-b used to build filters."""
    if granularity == "sentence":
        return {
            "from": _SENTENCE_FROM,
            "columns": _SENTENCE_COLUMNS,
            "id": "s.id",
            "score": "s.similarity",
            "method": "s.method",
            "lang_a": "s.text_a_lang",
            "lang_b": "s.text_b_lang",
        }
    if granularity == "chunk":
        return {
            "from": _CHUNK_FROM,
            "columns": _CHUNK_COLUMNS,
            "id": "p.id",
            "score": "p.confidence",
            "method": "p.method",
            "lang_a": "p.text_a_lang",
            "lang_b": "p.text_b_lang",
        }
    raise ValueError(f"unknown granularity: {granularity!r}")


def _filters(
    cfg: dict,
    *,
    min_confidence: float,
    langs: Sequence[str] | None,
    methods: Sequence[str] | None,
) -> tuple[str, dict, list[str]]:
    """Build the shared WHERE clause. Returns (where_sql, params, expanding).

    ``expanding`` names the params that need ``bindparam(..., expanding=True)``
    (the ``IN`` lists). ``min_confidence`` filters ``confidence`` (chunk) or
    ``similarity`` (sentence) — the analogous quality score for each store.
    """
    clauses = [f"{cfg['score']} >= :min_confidence"]
    params: dict = {"min_confidence": min_confidence}
    expanding: list[str] = []
    if methods:
        clauses.append(f"{cfg['method']} IN :methods")
        params["methods"] = list(methods)
        expanding.append("methods")
    if langs:
        clauses.append(f"({cfg['lang_a']} || '-' || {cfg['lang_b']}) IN :langs")
        params["langs"] = list(langs)
        expanding.append("langs")
    return " AND ".join(clauses), params, expanding


def _stmt(sql: str, expanding: Iterable[str]):
    stmt = text(sql)
    binds = [bindparam(name, expanding=True) for name in expanding]
    return stmt.bindparams(*binds) if binds else stmt


# ---------------------------------------------------------------------------
# Pure builders (unit-tested without a DB)
# ---------------------------------------------------------------------------


def _license_obj(spdx, url) -> dict | None:
    if not spdx and not url:
        return None
    return {"spdx": spdx, "url": url}


def _attribution(name_zh, name_en, spdx) -> str | None:
    name = name_en or name_zh
    if not name and not spdx:
        return None
    if name and spdx:
        return f"{name} ({spdx})"
    return name or spdx


def chunk_row_to_record(row) -> dict:
    """One ``alignment_pairs`` row → a JSONL record.

    Backward compatible: every field the pre-license export emitted is kept;
    the only additions are the ``license`` + ``attribution`` keys nested inside
    ``src`` / ``tgt``.
    """
    return {
        "id": row.id,
        "lang_src": row.lang_src,
        "lang_tgt": row.lang_tgt,
        "src": {
            "text_id": row.src_text_id,
            "canonical_id": row.src_canonical_id,
            "title": row.src_title,
            "juan": row.src_juan,
            "chunk_index": row.src_chunk,
            "license": _license_obj(row.src_license_spdx, row.src_license_url),
            "attribution": _attribution(
                row.src_source_name_zh, row.src_source_name_en, row.src_license_spdx
            ),
        },
        "tgt": {
            "text_id": row.tgt_text_id,
            "canonical_id": row.tgt_canonical_id,
            "title": row.tgt_title,
            "juan": row.tgt_juan,
            "chunk_index": row.tgt_chunk,
            "license": _license_obj(row.tgt_license_spdx, row.tgt_license_url),
            "attribution": _attribution(
                row.tgt_source_name_zh, row.tgt_source_name_en, row.tgt_license_spdx
            ),
        },
        "segment_src": row.segment_src,
        "segment_tgt": row.segment_tgt,
        "confidence": row.confidence,
        "method": row.method,
        "verified": row.is_verified,
    }


def sentence_row_to_record(row) -> dict:
    """One ``sentence_alignments`` row → a JSONL record."""
    return {
        "id": row.id,
        "align_type": row.align_type,
        "similarity": row.similarity,
        "method": row.method,
        "src": {
            "text_id": row.src_text_id,
            "title": row.src_title,
            "juan": row.src_juan,
            "char_start": row.src_char_start,
            "char_end": row.src_char_end,
            "lang": row.src_lang,
            "text": row.src_text,
            "license": _license_obj(row.src_license_spdx, row.src_license_url),
            "attribution": _attribution(
                row.src_source_name_zh, row.src_source_name_en, row.src_license_spdx
            ),
        },
        "tgt": {
            "text_id": row.tgt_text_id,
            "title": row.tgt_title,
            "juan": row.tgt_juan,
            "char_start": row.tgt_char_start,
            "char_end": row.tgt_char_end,
            "lang": row.tgt_lang,
            "text": row.tgt_text,
            "license": _license_obj(row.tgt_license_spdx, row.tgt_license_url),
            "attribution": _attribution(
                row.tgt_source_name_zh, row.tgt_source_name_en, row.tgt_license_spdx
            ),
        },
    }


def _row_to_record(granularity: str, row) -> dict:
    return sentence_row_to_record(row) if granularity == "sentence" else chunk_row_to_record(row)


def aggregate_source_licenses(rows: Iterable) -> list[dict]:
    """Collapse per-side license rows into the distinct source-license list for
    the card. Each row is ``(spdx, url, name_zh, name_en, attribution_required)``
    (accessed positionally). Rows with neither a name nor an SPDX are dropped;
    duplicates are merged, keyed on (source-name, spdx). Deterministically sorted.
    """
    seen: dict[tuple, dict] = {}
    for r in rows:
        spdx, url, name_zh, name_en, attr_required = r[0], r[1], r[2], r[3], r[4]
        name = name_en or name_zh
        if not name and not spdx:
            continue
        key = (name or "", spdx or "")
        if key not in seen:
            seen[key] = {
                "source": name,
                "spdx": spdx,
                "url": url,
                "attribution_required": bool(attr_required) if attr_required is not None else None,
            }
    return [seen[k] for k in sorted(seen)]


def build_card(
    *,
    granularity: str,
    version: str | None,
    generated_at: str | None,
    record_count: int,
    source_licenses: list[dict],
) -> dict:
    """Assemble the dataset card (the first JSONL line).

    ``generated_at`` is caller-supplied (the runtime forbids wall-clock reads in
    some contexts) and omitted when ``None``. ``version`` falls back to
    ``DEFAULT_VERSION``.
    """
    ver = version or DEFAULT_VERSION
    card: dict = {
        "dataset": DATASET_NAME,
        "version": ver,
    }
    if generated_at:
        card["generated_at"] = generated_at
    card["record_count"] = record_count
    card["granularity"] = granularity
    card["license"] = DATASET_LICENSE
    card["source_licenses"] = source_licenses
    card["provenance_note"] = PROVENANCE_NOTE
    card["citation"] = _CITATION_TEMPLATE.format(version=ver)
    return card


# ---------------------------------------------------------------------------
# DB orchestration (streaming; each batch in its own short-lived session)
# ---------------------------------------------------------------------------


async def _fetch(session_factory: SessionFactory, stmt, params: dict):
    async with session_factory() as session:  # type: ignore[operator]
        result = await session.execute(stmt, params)
        return result.fetchall()


async def collect_card_facts(
    *,
    granularity: str,
    min_confidence: float = 0.0,
    langs: Sequence[str] | None = None,
    methods: Sequence[str] | None = None,
    session_factory: SessionFactory = async_session,
) -> tuple[int, list[dict]]:
    """Server-side aggregate: (record_count, distinct source-license list).

    Three tiny aggregate queries — a COUNT and one DISTINCT-source query per
    side — none of which stream row bodies back to Python.
    """
    cfg = _config(granularity)
    where, params, expanding = _filters(
        cfg, min_confidence=min_confidence, langs=langs, methods=methods
    )

    count_rows = await _fetch(
        session_factory, _stmt(f"SELECT COUNT(*) {cfg['from']} WHERE {where}", expanding), params
    )
    record_count = int(count_rows[0][0]) if count_rows else 0

    lic_cols = "license_spdx, license_url, name_zh, name_en, attribution_required"
    lic_rows: list = []
    for side in ("sa", "sb"):
        sql = (
            f"SELECT DISTINCT {', '.join(f'{side}.{c}' for c in lic_cols.split(', '))} "
            f"{cfg['from']} WHERE {where}"
        )
        lic_rows.extend(await _fetch(session_factory, _stmt(sql, expanding), params))

    return record_count, aggregate_source_licenses(lic_rows)


async def iter_records(
    *,
    granularity: str,
    min_confidence: float = 0.0,
    langs: Sequence[str] | None = None,
    methods: Sequence[str] | None = None,
    batch_size: int = DEFAULT_BATCH,
    session_factory: SessionFactory = async_session,
) -> AsyncIterator[dict]:
    """Yield JSONL records, keyset-paginated on the primary id. Memory stays
    bounded to one ``batch_size`` slice regardless of table size."""
    cfg = _config(granularity)
    where, base_params, expanding = _filters(
        cfg, min_confidence=min_confidence, langs=langs, methods=methods
    )
    sql = (
        f"SELECT {cfg['columns']} {cfg['from']} "
        f"WHERE {where} AND {cfg['id']} > :last_id "
        f"ORDER BY {cfg['id']} LIMIT :batch"
    )
    stmt = _stmt(sql, expanding)

    last_id = 0
    while True:
        params = {**base_params, "last_id": last_id, "batch": batch_size}
        rows = await _fetch(session_factory, stmt, params)
        if not rows:
            break
        for row in rows:
            yield _row_to_record(granularity, row)
        last_id = rows[-1].id


async def compute_stats(
    *,
    granularity: str,
    min_confidence: float = 0.0,
    langs: Sequence[str] | None = None,
    methods: Sequence[str] | None = None,
    session_factory: SessionFactory = async_session,
) -> list[dict]:
    """Distribution for ``--stats`` (server-side GROUP BY, no row bodies).

    Chunk: grouped by language pair with the average confidence.
    Sentence: grouped by ``align_type`` with the average similarity.
    """
    cfg = _config(granularity)
    where, params, expanding = _filters(
        cfg, min_confidence=min_confidence, langs=langs, methods=methods
    )
    if granularity == "sentence":
        group_expr = "s.align_type"
        label = "align_type"
    else:
        group_expr = f"({cfg['lang_a']} || '-' || {cfg['lang_b']})"
        label = "langs"
    sql = (
        f"SELECT {group_expr} AS grp, COUNT(*) AS n, AVG({cfg['score']}) AS avg_score "
        f"{cfg['from']} WHERE {where} GROUP BY {group_expr} ORDER BY n DESC"
    )
    rows = await _fetch(session_factory, _stmt(sql, expanding), params)
    return [
        {label: grp, "count": int(n), "avg_score": float(avg) if avg is not None else None}
        for grp, n, avg in rows
    ]


async def iter_jsonl(
    *,
    granularity: str,
    version: str | None = None,
    generated_at: str | None = None,
    min_confidence: float = 0.0,
    langs: Sequence[str] | None = None,
    methods: Sequence[str] | None = None,
    batch_size: int = DEFAULT_BATCH,
    session_factory: SessionFactory = async_session,
) -> AsyncIterator[str]:
    """Full JSONL stream: the dataset card as line 1, then one line per record.

    Used by the HTTP endpoint. Each yielded string is a complete line (``\\n``
    terminated).
    """
    record_count, source_licenses = await collect_card_facts(
        granularity=granularity,
        min_confidence=min_confidence,
        langs=langs,
        methods=methods,
        session_factory=session_factory,
    )
    card = build_card(
        granularity=granularity,
        version=version,
        generated_at=generated_at,
        record_count=record_count,
        source_licenses=source_licenses,
    )
    yield json.dumps(card, ensure_ascii=False) + "\n"

    async for rec in iter_records(
        granularity=granularity,
        min_confidence=min_confidence,
        langs=langs,
        methods=methods,
        batch_size=batch_size,
        session_factory=session_factory,
    ):
        yield json.dumps(rec, ensure_ascii=False) + "\n"
