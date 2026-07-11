"""Refine chunk-level alignment_pairs into sentence-level sentence_alignments.

A chunk-level pair says "this paragraph in canon A parallels that paragraph in
canon B". This job SUBDIVIDES each such pair into aligned SENTENCE pairs and
writes them to the dedicated ``sentence_alignments`` table (migration 0170),
leaving ``alignment_pairs`` and every chunk-level consumer untouched.

Per chunk-level pair:
  1. Load each side's text. Preferred: the 0168 char offsets
     (text_{a,b}_char_start/_end) slice the side's juan from
     ``text_contents.content`` — for pi/bo this is the ORIGINAL Pāli/Tibetan, the
     right thing to sentence-split. Fallback: if a side's offsets are still NULL
     (parent pair not yet backfilled) use that chunk's ``text_embeddings.chunk_text``
     with base offset 0 — degraded (chunk-relative offsets; and for pi/bo the
     chunk_text is an English translation), so it is counted separately.
  2. ``split_sentences`` each side (offset-preserving), then ``embed_and_align``
     (one batched BGE-M3 call per pair) to get sentence pairs.
  3. INSERT ... ON CONFLICT DO NOTHING on uq_sentence_align → idempotent re-runs.
     ``source_pair_id`` records provenance.

Follows the established offline-backfill pattern (import_mitra_alignments.py,
backfill_mitra_scores.py): a single dedicated NullPool connection for the whole
run (fojin's prod Postgres is connection-starved and a pooled session's
re-checkout after commit can fail mid-run), batched writes, --dry-run, progress
+ throughput + summary. Do NOT point this at a live DB / embedding API casually.

Usage (inside backend container, DB + embedding API reachable):
    python scripts/refine_sentence_alignments.py --dry-run --limit 50
    python scripts/refine_sentence_alignments.py --method-filter embed_llm,manual,expert
    python scripts/refine_sentence_alignments.py --pair-key 12345      # one pair by id
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import bindparam
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.exceptions import EmbeddingServiceError
from app.services.sentence_align import (
    MAX_SENTENCES_PER_CHUNK,
    AlignedPair,
    embed_and_align,
    sentence_align_key,
    split_sentences,
)

METHOD = "sentence-bertalign"
_CONTENT_CACHE_MAX = 64

# Chunk-level pairs only (text_a_chunk_index IS NOT NULL); a method filter and a
# single-pair filter are appended in main().
SELECT_PAIRS = """
    SELECT id,
           text_a_id, text_a_juan_num, text_a_chunk_index, text_a_lang,
           text_a_char_start, text_a_char_end,
           text_b_id, text_b_juan_num, text_b_chunk_index, text_b_lang,
           text_b_char_start, text_b_char_end
    FROM alignment_pairs
    WHERE text_a_chunk_index IS NOT NULL
"""

INSERT_SENTENCE = sql_text(
    """
    INSERT INTO sentence_alignments
      (source_pair_id,
       text_a_id, text_a_juan_num, text_a_char_start, text_a_char_end, text_a_lang, sent_a_text,
       text_b_id, text_b_juan_num, text_b_char_start, text_b_char_end, text_b_lang, sent_b_text,
       similarity, align_type, method)
    VALUES
      (:source_pair_id,
       :text_a_id, :text_a_juan_num, :text_a_char_start, :text_a_char_end, :text_a_lang, :sent_a_text,
       :text_b_id, :text_b_juan_num, :text_b_char_start, :text_b_char_end, :text_b_lang, :sent_b_text,
       :similarity, :align_type, :method)
    ON CONFLICT (text_a_id, text_a_juan_num, text_a_char_start,
                 text_b_id, text_b_juan_num, text_b_char_start)
    DO NOTHING
    """
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_sentence_align.py)
# ---------------------------------------------------------------------------


def parse_method_filter(raw: str | None) -> list[str] | None:
    """Comma-separated --method-filter → cleaned list, or None for "all"."""
    if not raw:
        return None
    methods = [m.strip() for m in raw.split(",") if m.strip()]
    return methods or None


def pick_content(rows: list[tuple[str, str]], side_lang: str | None) -> str | None:
    """The text_contents row a side's offsets index into: the side-lang row when
    present, else the juan's only row; multiple rows with no lang match → None
    (which content the offset indexes would be ambiguous). Mirrors
    backfill_alignment_offsets.pick_content so both anchor the same way."""
    for lang, content in rows:
        if side_lang and lang == side_lang:
            return content
    if len(rows) == 1:
        return rows[0][1]
    return None


def build_insert_rows(
    *,
    source_pair_id: int,
    text_a_id: int,
    text_a_juan_num: int,
    text_a_lang: str,
    text_b_id: int,
    text_b_juan_num: int,
    text_b_lang: str,
    aligned: list[AlignedPair],
    method: str,
    seen: set[tuple],
) -> list[dict]:
    """Turn aligned sentence pairs into INSERT dicts, deduping by the
    uq_sentence_align identity against ``seen`` (mutated) so a write batch never
    carries a self-conflict. Pure given ``seen``."""
    out: list[dict] = []
    for pair in aligned:
        key = sentence_align_key(
            text_a_id, text_a_juan_num, pair.a_char_start,
            text_b_id, text_b_juan_num, pair.b_char_start,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source_pair_id": source_pair_id,
            "text_a_id": text_a_id,
            "text_a_juan_num": text_a_juan_num,
            "text_a_char_start": pair.a_char_start,
            "text_a_char_end": pair.a_char_end,
            "text_a_lang": text_a_lang,
            "sent_a_text": pair.sent_a_text,
            "text_b_id": text_b_id,
            "text_b_juan_num": text_b_juan_num,
            "text_b_char_start": pair.b_char_start,
            "text_b_char_end": pair.b_char_end,
            "text_b_lang": text_b_lang,
            "sent_b_text": pair.sent_b_text,
            "similarity": pair.similarity,
            "align_type": pair.align_type,
            "method": method,
        })
    return out


# ---------------------------------------------------------------------------
# DB glue
# ---------------------------------------------------------------------------


class _ContentCache:
    """Tiny LRU over text_contents juans: (text_id, juan_num) -> [(lang, content)]."""

    def __init__(self, conn):
        self._conn = conn
        self._cache: OrderedDict[tuple[int, int], list[tuple[str, str]]] = OrderedDict()

    async def get(self, text_id: int, juan_num: int) -> list[tuple[str, str]]:
        key = (text_id, juan_num)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        rows = (await self._conn.execute(
            sql_text(
                "SELECT lang, content FROM text_contents "
                "WHERE text_id = :tid AND juan_num = :juan ORDER BY lang"
            ),
            {"tid": text_id, "juan": juan_num},
        )).fetchall()
        value = [(r[0], r[1] or "") for r in rows]
        self._cache[key] = value
        if len(self._cache) > _CONTENT_CACHE_MAX:
            self._cache.popitem(last=False)
        return value


async def _chunk_text(conn, tid: int, juan: int, cidx: int) -> str | None:
    row = (await conn.execute(
        sql_text(
            "SELECT chunk_text FROM text_embeddings "
            "WHERE text_id = :tid AND juan_num = :juan AND chunk_index = :cidx"
        ),
        {"tid": tid, "juan": juan, "cidx": cidx},
    )).first()
    return (row[0] or "") if row else None


async def _load_side(
    conn,
    contents: _ContentCache,
    stats: Counter,
    *,
    tid: int,
    juan: int,
    cidx: int,
    lang: str | None,
    char_start: int | None,
    char_end: int | None,
) -> tuple[str, int] | None:
    """Return (buffer_text, base_offset) for one side, or None if no text at all.

    Preferred path uses the 0168 char offsets to slice the juan content (base
    offset = char_start, so split offsets are juan-absolute). Falls back to the
    chunk_text buffer (base offset 0) when offsets are NULL or the content row is
    missing/ambiguous, counting the degradation.
    """
    if char_start is not None and char_end is not None:
        content = pick_content(await contents.get(tid, juan), lang)
        if content:
            span = content[char_start:char_end]
            if span:
                return span, char_start
    # Fallback: chunk_text buffer, chunk-relative offsets.
    ct = await _chunk_text(conn, tid, juan, cidx)
    if ct:
        stats["no_offset_fallback_sides"] += 1
        return ct, 0
    return None


async def _flush(conn, rows: list[dict], dry_run: bool) -> None:
    if rows and not dry_run:
        await conn.execute(INSERT_SENTENCE, rows)
        await conn.commit()


async def run_refine(
    conn,
    *,
    method_filter: list[str] | None,
    limit: int | None,
    pair_key: int | None,
    batch_size: int,
    dry_run: bool,
    log_every: int,
    embed_fn=None,
) -> Counter:
    """Refine matching chunk pairs into sentence pairs. Returns summary stats."""
    select_sql = SELECT_PAIRS
    params: dict = {}
    if pair_key is not None:
        select_sql += " AND id = :pair_key"
        params["pair_key"] = pair_key
    if method_filter:
        select_sql += " AND method IN :methods"
    select_sql += " ORDER BY id"
    if limit:
        select_sql += " LIMIT :lim"
        params["lim"] = limit

    stmt = sql_text(select_sql)
    if method_filter:
        stmt = stmt.bindparams(bindparam("methods", expanding=True))
        params["methods"] = method_filter
    pairs = (await conn.execute(stmt, params)).fetchall()

    stats: Counter = Counter()
    stats["pairs_total"] = len(pairs)
    print(f"chunk pairs to refine: {len(pairs)}; dry_run={dry_run}")

    contents = _ContentCache(conn)
    seen: set[tuple] = set()
    pending: list[dict] = []
    t0 = time.time()

    for idx, row in enumerate(pairs, start=1):
        (pid,
         a_tid, a_juan, a_cidx, a_lang, a_cs, a_ce,
         b_tid, b_juan, b_cidx, b_lang, b_cs, b_ce) = row

        buf_a = await _load_side(
            conn, contents, stats,
            tid=a_tid, juan=a_juan, cidx=a_cidx, lang=a_lang, char_start=a_cs, char_end=a_ce,
        )
        buf_b = await _load_side(
            conn, contents, stats,
            tid=b_tid, juan=b_juan, cidx=b_cidx, lang=b_lang, char_start=b_cs, char_end=b_ce,
        )
        if buf_a is None or buf_b is None:
            stats["skipped_no_content"] += 1
            continue

        sents_a = split_sentences(buf_a[0], a_lang or "", base_offset=buf_a[1])
        sents_b = split_sentences(buf_b[0], b_lang or "", base_offset=buf_b[1])
        if not sents_a or not sents_b:
            stats["skipped_no_sentences"] += 1
            continue
        if len(sents_a) > MAX_SENTENCES_PER_CHUNK or len(sents_b) > MAX_SENTENCES_PER_CHUNK:
            stats["skipped_too_large"] += 1
            continue

        try:
            aligned = await embed_and_align(sents_a, sents_b, embed_fn=embed_fn)
        except EmbeddingServiceError as exc:
            stats["skipped_embed_error"] += 1
            print(f"  pair {pid}: embedding failed ({exc}); skipped")
            continue

        rows = build_insert_rows(
            source_pair_id=pid,
            text_a_id=a_tid, text_a_juan_num=a_juan, text_a_lang=a_lang or "",
            text_b_id=b_tid, text_b_juan_num=b_juan, text_b_lang=b_lang or "",
            aligned=aligned, method=METHOD, seen=seen,
        )
        pending.extend(rows)
        stats["pairs_processed"] += 1
        stats["sentences_aligned"] += len(rows)

        if len(pending) >= batch_size:
            await _flush(conn, pending, dry_run)
            pending = []

        if idx % log_every == 0 or idx == len(pairs):
            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0.0
            print(
                f"  progress: {idx}/{len(pairs)} pairs "
                f"({stats['sentences_aligned']} sentence pairs) rate={rate:.1f} pairs/s"
            )

    await _flush(conn, pending, dry_run)
    return stats


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--method-filter",
        default=None,
        help="comma-separated alignment_pairs.method values to include (default: all)",
    )
    ap.add_argument("--limit", type=int, default=None, help="max chunk pairs to process")
    ap.add_argument("--pair-key", type=int, default=None, help="process only this alignment_pairs.id")
    ap.add_argument("--batch-size", type=int, default=500, help="sentence rows per INSERT/commit batch")
    ap.add_argument("--dry-run", action="store_true", help="align + report, no writes")
    ap.add_argument("--log-every", type=int, default=50, help="log progress every N pairs (default 50)")
    return ap


async def main() -> int:
    args = _build_parser().parse_args()
    if args.batch_size < 1:
        print("ERROR: --batch-size must be >= 1")
        return 1

    method_filter = parse_method_filter(args.method_filter)
    t0 = time.time()

    # Dedicated NullPool engine + one held connection, same rationale as
    # import_mitra_alignments.py (connection-starved prod Postgres).
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            stats = await run_refine(
                conn,
                method_filter=method_filter,
                limit=args.limit,
                pair_key=args.pair_key,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                log_every=args.log_every,
            )
    finally:
        await engine.dispose()

    print(
        "DONE in {:.1f}s ({}): pairs_processed={} sentences_aligned={} "
        "skipped_no_content={} skipped_no_sentences={} skipped_too_large={} "
        "skipped_embed_error={} no_offset_fallback_sides={}".format(
            time.time() - t0,
            "dry-run, no writes" if args.dry_run else "committed",
            stats["pairs_processed"], stats["sentences_aligned"],
            stats["skipped_no_content"], stats["skipped_no_sentences"],
            stats["skipped_too_large"], stats["skipped_embed_error"],
            stats["no_offset_fallback_sides"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
