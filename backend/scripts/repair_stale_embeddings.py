"""Repair stale / truncated text_embeddings left over from pre-parser-fix parses.

Background
----------
Many juans were embedded BEFORE later parser fixes (the cb:div type="xu" /
御製序 burial bug — same class as T0251 #640, and the CONTENT_TAGS <item> bug
#561). Their text_embeddings rows hold only the preface or a partial body, while
text_contents was subsequently re-ingested with the full, correct body. The
normal generator (scripts/archive/misc/generate_embeddings.py) is incremental —
`if i not in existing` + `ON CONFLICT (text_id, juan_num, chunk_index) DO
NOTHING` — so it can NEVER overwrite the stale chunks; it only appends missing
tail indices, which would leave a corrupt "preface + body" mix.

Symptom that surfaced this: T0279 (八十華嚴, text_id=12) juan 1 embeds to 943
chars (Empress Wu's 大周新譯序) vs the 6,726-char 世主妙嚴品 body in
text_contents, so MITRA cross-lingual parallels can't localize there -> the
reader "跨藏对照" panel shows 0/2 for juan 1 even though the text has 24,543
parallels overall. The same staleness silently degrades semantic search / RAG
(chat) for the affected juans, which retrieve preface text instead of the sutra.

What this does
--------------
Finds every (text_id, juan_num) of an lzh (Chinese-canon) text whose embedded
character total is < RATIO of its current lzh text_contents length, then for each
such juan: recomputes embeddings from the CURRENT content and atomically
replaces the juan's rows (DELETE + INSERT in one short transaction, embeddings
computed first so the row-lock window stays tiny).

Idempotent & resumable: it commits per juan and the candidate set is recomputed
from the live ratio, so a re-run after an interruption skips already-fixed juans.
Re-embedding a healthy juan is harmless (same model BAAI/bge-m3, same content =>
same vectors), so the RATIO threshold only needs to avoid missing broken juans.

Usage (inside the fojin-backend container, DB + embedding API reachable):
    python scripts/repair_stale_embeddings.py --dry-run
    python scripts/repair_stale_embeddings.py
    python scripts/repair_stale_embeddings.py --ratio 0.9 --min-content 500
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.exceptions import EmbeddingServiceError
from app.services.embedding import chunk_text, generate_embeddings_batch

EMBED_BATCH_SIZE = 20   # chunks per embedding API call
MIN_CHUNK_LEN = 10      # mirror generate_embeddings: skip near-empty chunks
MAX_RETRY = 4           # per-batch retry on transient embedding API errors

INSERT = sql_text(
    "INSERT INTO text_embeddings (text_id, juan_num, chunk_index, chunk_text, embedding) "
    "VALUES (:text_id, :juan_num, :chunk_index, :chunk_text, CAST(:embedding AS vector))"
)


async def _find_candidates(conn, ratio: float, min_content: int):
    """(text_id, juan_num, content_chars, embedded_chars) needing repair."""
    rows = (
        await conn.execute(
            sql_text(
                """
                WITH emb AS (
                    SELECT text_id, juan_num, sum(length(chunk_text)) AS e
                    FROM text_embeddings GROUP BY text_id, juan_num
                ),
                con AS (
                    SELECT tc.text_id, tc.juan_num, length(tc.content) AS c
                    FROM text_contents tc
                    JOIN buddhist_texts bt ON bt.id = tc.text_id
                    WHERE tc.lang = 'lzh' AND bt.lang = 'lzh'
                      AND length(tc.content) > :minc
                )
                SELECT con.text_id, con.juan_num, con.c, COALESCE(emb.e, 0) AS e
                FROM con LEFT JOIN emb USING (text_id, juan_num)
                -- CAST is load-bearing: without it asyncpg/postgres infers the
                -- bound param's type from `$n * con.c` (integer) and truncates
                -- 0.9 -> 0, making the predicate `< 0` always false (0 rows).
                WHERE COALESCE(emb.e, 0) < CAST(:ratio AS double precision) * con.c
                ORDER BY con.text_id, con.juan_num
                """
            ),
            {"ratio": ratio, "minc": min_content},
        )
    ).fetchall()
    return [(int(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in rows]


async def _content_of(conn, text_id: int, juan_num: int) -> str | None:
    row = (
        await conn.execute(
            sql_text(
                "SELECT content FROM text_contents "
                "WHERE text_id = :tid AND juan_num = :jn AND lang = 'lzh' LIMIT 1"
            ),
            {"tid": text_id, "jn": juan_num},
        )
    ).fetchone()
    return row[0] if row else None


async def _embed_chunks(chunks: list[tuple[int, str]]) -> list[tuple[int, str, list[float]]]:
    """Embed (index, text) pairs in batches with retry. Returns (idx, text, vec)."""
    out: list[tuple[int, str, list[float]]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        texts = [c for _, c in batch]
        for attempt in range(1, MAX_RETRY + 1):
            try:
                vecs = await generate_embeddings_batch(texts)
                break
            except EmbeddingServiceError:
                if attempt == MAX_RETRY:
                    raise
                await asyncio.sleep(2 * attempt)
        for (idx, txt), vec in zip(batch, vecs, strict=True):
            out.append((idx, txt, vec))
    return out


async def _repair_one(conn, text_id: int, juan_num: int) -> int:
    """Recompute + atomically replace one juan's embeddings. Returns chunk count."""
    content = await _content_of(conn, text_id, juan_num)
    # SQLAlchemy 2.0 auto-begins a transaction on that SELECT and would hold its
    # snapshot + ACCESS SHARE lock across the whole HTTP embedding window below.
    # Close it now so the (possibly multi-second, retrying) embed call runs with
    # NO open transaction — important on this deliberately connection-starved PG.
    await conn.rollback()
    if not content:
        return 0
    # enumerate-then-filter keeps chunk_index == position in the full chunk list,
    # exactly matching generate_embeddings (so search / MITRA localization see the
    # same indexing scheme).
    chunks = [
        (i, c)
        for i, c in enumerate(chunk_text(content, chunk_size=500, overlap=50))
        if len(c.strip()) >= MIN_CHUNK_LEN
    ]
    if not chunks:
        # min_content > 500 makes this unreachable in practice (the first ~500-char
        # chunk always clears MIN_CHUNK_LEN); warn rather than DELETE, since
        # deleting with nothing to insert would leave the juan with zero vectors.
        logging.warning("text %d juan %d chunked to nothing — left untouched", text_id, juan_num)
        return 0

    # 1. Embed first (HTTP, runs with no open transaction after the rollback above).
    embedded = await _embed_chunks(chunks)

    # 2. Short transaction: drop the stale rows and insert fresh ones together,
    #    so the juan is never observed half-deleted. Commit persists progress.
    await conn.execute(
        sql_text("DELETE FROM text_embeddings WHERE text_id = :tid AND juan_num = :jn"),
        {"tid": text_id, "jn": juan_num},
    )
    await conn.execute(
        INSERT,
        [
            {
                "text_id": text_id,
                "juan_num": juan_num,
                "chunk_index": idx,
                "chunk_text": txt,
                "embedding": "[" + ",".join(str(x) for x in vec) + "]",
            }
            for idx, txt, vec in embedded
        ],
    )
    await conn.commit()
    return len(embedded)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ratio", type=float, default=0.9,
                    help="repair juans whose embedded chars < ratio * content chars")
    ap.add_argument("--min-content", type=int, default=500,
                    help="only consider lzh juans with content longer than this")
    ap.add_argument("--dry-run", action="store_true", help="report scope, write nothing")
    ap.add_argument("--limit", type=int, default=0, help="cap juans processed (0 = all)")
    args = ap.parse_args()

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    t0 = time.time()
    done = chunks_total = 0
    failed: list[tuple[int, int]] = []
    try:
        async with engine.connect() as conn:
            cands = await _find_candidates(conn, args.ratio, args.min_content)
            await conn.rollback()  # close the read tx auto-begun by the candidate query
            miss = sum(c - e for _, _, c, e in cands)
            repaired_text_ids: set[int] = set()
            print(
                f"candidates: {len(cands)} juans across "
                f"{len({t for t, _, _, _ in cands})} texts; "
                f"~{miss:,} missing content chars; ratio<{args.ratio} "
                f"min_content>{args.min_content}",
                flush=True,
            )
            if args.dry_run:
                for tid, jn, c, e in cands[:25]:
                    print(f"  text {tid} juan {jn}: embedded {e}/{c} "
                          f"({round(100 * e / c)}%)", flush=True)
                if len(cands) > 25:
                    print(f"  ... +{len(cands) - 25} more", flush=True)
                return 0

            targets = cands[: args.limit] if args.limit else cands
            for tid, jn, _c, _e in targets:
                try:
                    n = await _repair_one(conn, tid, jn)
                    done += 1
                    chunks_total += n
                    if n:
                        repaired_text_ids.add(tid)
                except Exception as exc:  # one bad juan must not abort the run
                    await conn.rollback()
                    failed.append((tid, jn))
                    print(f"  FAILED text {tid} juan {jn}: "
                          f"{type(exc).__name__}: {exc}", flush=True)
                if done % 25 == 0 and done:
                    rate = done / (time.time() - t0)
                    print(f"  progress {done}/{len(targets)} juans, "
                          f"{chunks_total} chunks, {rate:.1f} juan/s", flush=True)
    finally:
        await engine.dispose()

    print(f"DONE: repaired {done} juans, {chunks_total} chunks in "
          f"{time.time() - t0:.0f}s; failed {len(failed)}", flush=True)
    # Re-embedding renumbers a juan's chunks, so chunk_index references CAPTURED by
    # alignment_pairs (build_alignments.py) and mitra_alignments
    # (import_mitra_alignments.py) for a repaired juan now point at the new scheme.
    # Semantic search / RAG is fixed immediately (they read text_embeddings live),
    # but cross-canon alignment for these texts must be rebuilt to re-localize and
    # to surface parallels the stale (preface-only) chunks had blocked.
    if repaired_text_ids:
        ids = ",".join(str(t) for t in sorted(repaired_text_ids))
        print(
            f"NEXT: re-run alignment for the {len(repaired_text_ids)} repaired "
            f"text(s) so cross-canon parallels re-localize against the new chunks:\n"
            f"  - import_mitra_alignments.py --taisho <their Taishō ids>\n"
            f"  - build_alignments.py for the same texts (fojin↔fojin pairs)\n"
            f"repaired text_ids: {ids}",
            flush=True,
        )
    if failed:
        print("FAILED:", ", ".join(f"{t}/{j}" for t, j in failed[:40]), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
