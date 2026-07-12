"""Backfill char-offset anchors onto alignment_pairs (columns from migration 0168).

alignment_pairs references chunks POSITIONALLY (text_id, juan_num, chunk_index)
with no FK — a re-chunking silently invalidates every pair. Migration 0168
added nullable text_{a,b}_char_start/_char_end columns: offsets into the
juan's text_contents.content, which survive re-chunking. This script fills
them for existing rows.

Per side of each chunk-level pair whose offsets are NULL:
  1. Load the side's chunk_text from text_embeddings and the juan content from
     text_contents (the row whose lang matches the side's lang; if that row is
     absent, the juan's single content row when there is exactly one —
     otherwise the anchor would be ambiguous about WHICH content it indexes).
  2. Locate the chunk verbatim in the content; fall back to normalized
     matching (strip whitespace/punct/latin/digits — the same normalization
     the MITRA importer uses) with the match mapped back to original offsets.
  3. A needle found at more than one position is AMBIGUOUS and skipped, never
     guessed (same stance as the MITRA importer's cross-juan gate).

Idempotent: only rows with a NULL char_start on either side are selected, and
the UPDATE COALESCEs so an already-backfilled side is never overwritten.

Usage (inside backend container, DB reachable):
    python scripts/backfill_alignment_offsets.py --dry-run
    python scripts/backfill_alignment_offsets.py --limit 500
    python scripts/backfill_alignment_offsets.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import bindparam
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# Same normalization as scripts/import_mitra_alignments.py: strip whitespace,
# CJK/Latin punctuation, latin letters and digits so edition-level punctuation
# variance doesn't break the match.
_PUNCT = re.compile(r"[\s　，。、；：！？·「」『』（）()．,0-9A-Za-z\-—…〈〉《》【】\[\]]+")

# Content rows cached per (text_id, juan_num); rows are grouped by text/juan in
# the scan so a small cache absorbs nearly all repeats without holding a whole
# canon in memory on the VPS.
_CONTENT_CACHE_MAX = 64

SELECT_TARGETS = """
    SELECT id,
           text_a_id, text_a_juan_num, text_a_chunk_index, text_a_lang,
           text_a_char_start,
           text_b_id, text_b_juan_num, text_b_chunk_index, text_b_lang,
           text_b_char_start
    FROM alignment_pairs
    WHERE text_a_chunk_index IS NOT NULL
      AND (text_a_char_start IS NULL OR text_b_char_start IS NULL)
    ORDER BY text_a_id, text_a_juan_num, id
"""

# COALESCE keeps any side that is already backfilled (or that this run could
# not locate) untouched — re-runs are safe.
UPDATE_OFFSETS = sql_text(
    """
    UPDATE alignment_pairs
    SET text_a_char_start = COALESCE(text_a_char_start, :a_start),
        text_a_char_end   = COALESCE(text_a_char_end, :a_end),
        text_b_char_start = COALESCE(text_b_char_start, :b_start),
        text_b_char_end   = COALESCE(text_b_char_end, :b_end)
    WHERE id = :id
    """
)


def normalize_with_map(s: str) -> tuple[str, list[int]]:
    """Normalized copy of ``s`` plus a map from each kept char back to its
    original index, so a match in normalized space converts to original-content
    char offsets."""
    kept: list[str] = []
    idx_map: list[int] = []
    for i, ch in enumerate(s):
        if not _PUNCT.match(ch):
            kept.append(ch)
            idx_map.append(i)
    return "".join(kept), idx_map


_AMBIGUOUS = -1


def _find_unique(haystack: str, needle: str) -> int | None:
    """Index of a unique occurrence of ``needle``: None if absent,
    ``_AMBIGUOUS`` (-1) if it occurs more than once."""
    pos = haystack.find(needle)
    if pos < 0:
        return None
    if haystack.find(needle, pos + 1) >= 0:
        return _AMBIGUOUS
    return pos


def locate_span(content: str, needle: str) -> tuple[str, int | None, int | None]:
    """Locate ``needle`` (a chunk_text) inside ``content`` (a juan's text).

    Returns (status, char_start, char_end) with char_end exclusive.
    status: "verbatim" | "normalized" | "ambiguous" | "not_found" | "empty".
    Offsets are only returned for a unique match — an ambiguous needle is
    skipped, never guessed.
    """
    if not content or not needle:
        return "empty", None, None

    pos = _find_unique(content, needle)
    if pos == _AMBIGUOUS:
        return "ambiguous", None, None
    if pos is not None:
        return "verbatim", pos, pos + len(needle)

    norm_needle = _PUNCT.sub("", needle)
    if not norm_needle:
        return "empty", None, None
    norm_content, idx_map = normalize_with_map(content)
    pos = _find_unique(norm_content, norm_needle)
    if pos == _AMBIGUOUS:
        return "ambiguous", None, None
    if pos is None:
        return "not_found", None, None
    start = idx_map[pos]
    end = idx_map[pos + len(norm_needle) - 1] + 1
    return "normalized", start, end


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
        rows = (
            await self._conn.execute(
                sql_text(
                    "SELECT lang, content FROM text_contents "
                    "WHERE text_id = :tid AND juan_num = :juan ORDER BY lang"
                ),
                {"tid": text_id, "juan": juan_num},
            )
        ).fetchall()
        value = [(r[0], r[1] or "") for r in rows]
        self._cache[key] = value
        if len(self._cache) > _CONTENT_CACHE_MAX:
            self._cache.popitem(last=False)
        return value


def pick_content(rows: list[tuple[str, str]], side_lang: str | None) -> str | None:
    """The content row a side's offsets index into: the side-lang row when
    present, else the juan's only row. Multiple rows with no lang match →
    None (writing an offset without knowing which content it indexes would be
    a corrupt anchor)."""
    for lang, content in rows:
        if side_lang and lang == side_lang:
            return content
    if len(rows) == 1:
        return rows[0][1]
    return None


async def _chunk_texts(conn, keys: set[tuple[int, int, int]]) -> dict[tuple, str]:
    """Batched chunk_text fetch for one scan batch (expanding tuple-IN, the
    same pattern the alignment juan endpoint uses against prod Postgres)."""
    if not keys:
        return {}
    rows = (
        await conn.execute(
            sql_text(
                "SELECT text_id, juan_num, chunk_index, chunk_text FROM text_embeddings "
                "WHERE (text_id, juan_num, chunk_index) IN :keys"
            ).bindparams(bindparam("keys", expanding=True)),
            {"keys": list(keys)},
        )
    ).fetchall()
    return {(r[0], r[1], r[2]): r[3] or "" for r in rows}


async def _locate_side(
    stats: Counter,
    contents: _ContentCache,
    te_map: dict[tuple, str],
    tid: int,
    juan: int,
    cidx: int,
    lang: str | None,
) -> tuple[int | None, int | None]:
    chunk_text = te_map.get((tid, juan, cidx))
    if chunk_text is None:
        stats["no_chunk"] += 1
        return None, None
    content = pick_content(await contents.get(tid, juan), lang)
    if content is None:
        stats["no_content"] += 1
        return None, None
    status, start, end = locate_span(content, chunk_text)
    stats[status] += 1
    return start, end


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="locate + report, no writes")
    ap.add_argument("--limit", type=int, default=None, help="max alignment_pairs rows to process")
    ap.add_argument("--batch-size", type=int, default=500, help="rows per UPDATE/commit batch")
    args = ap.parse_args()

    t0 = time.time()
    stats: Counter = Counter()
    updated = scanned = 0

    # Dedicated NullPool engine + one long-lived connection, same rationale as
    # import_mitra_alignments.py: on fojin's connection-starved Postgres a
    # pooled session's re-checkout after each commit can fail mid-run.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            select_sql = SELECT_TARGETS + (" LIMIT :lim" if args.limit else "")
            params = {"lim": args.limit} if args.limit else {}
            targets = (await conn.execute(sql_text(select_sql), params)).fetchall()
            total = len(targets)
            print(f"targets: {total} alignment_pairs rows; dry_run={args.dry_run}")

            contents = _ContentCache(conn)
            for batch_start in range(0, total, args.batch_size):
                batch = targets[batch_start : batch_start + args.batch_size]
                te_keys = set()
                for row in batch:
                    (_pid, a_tid, a_juan, a_cidx, _a_lang, a_start,
                     b_tid, b_juan, b_cidx, _b_lang, b_start) = row
                    if a_start is None:
                        te_keys.add((a_tid, a_juan, a_cidx))
                    if b_start is None and b_cidx is not None:
                        te_keys.add((b_tid, b_juan, b_cidx))
                te_map = await _chunk_texts(conn, te_keys)

                updates: list[dict] = []
                for row in batch:
                    (pid, a_tid, a_juan, a_cidx, a_lang, a_start,
                     b_tid, b_juan, b_cidx, b_lang, b_start) = row
                    scanned += 1
                    new_a = (None, None)
                    new_b = (None, None)
                    if a_start is None:
                        new_a = await _locate_side(
                            stats, contents, te_map, a_tid, a_juan, a_cidx, a_lang
                        )
                    if b_start is None and b_cidx is not None:
                        new_b = await _locate_side(
                            stats, contents, te_map, b_tid, b_juan, b_cidx, b_lang
                        )
                    if new_a[0] is not None or new_b[0] is not None:
                        updates.append(
                            {
                                "id": pid,
                                "a_start": new_a[0], "a_end": new_a[1],
                                "b_start": new_b[0], "b_end": new_b[1],
                            }
                        )

                if updates and not args.dry_run:
                    await conn.execute(UPDATE_OFFSETS, updates)
                    await conn.commit()
                updated += len(updates)
                print(
                    f"  progress: {min(batch_start + args.batch_size, total)}/{total} rows scanned, "
                    f"{updated} rows updated"
                )
    finally:
        await engine.dispose()

    located = stats["verbatim"] + stats["normalized"]
    print(
        f"DONE in {time.time() - t0:.1f}s: scanned={scanned} rows, updated={updated} rows "
        f"({'dry-run, no writes' if args.dry_run else 'committed'})"
    )
    print(
        "  sides: located={} (verbatim={} normalized={}) ambiguous={} not_found={} "
        "empty={} no_chunk={} no_content={}".format(
            located, stats["verbatim"], stats["normalized"], stats["ambiguous"],
            stats["not_found"], stats["empty"], stats["no_chunk"], stats["no_content"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
