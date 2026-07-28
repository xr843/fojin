"""Repair stale text_embeddings whose chunks no longer match their juan's content.

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

The same re-ingest leaves TWO opposite shapes behind, and both are corruption:

* **Under-embedded** — chunks cover less than the juan. Symptom that surfaced
  this: T0279 (八十華嚴, text_id=12) juan 1 embeds to 943 chars (Empress Wu's
  大周新譯序) vs the 6,726-char 世主妙嚴品 body, so MITRA parallels can't
  localize and RAG retrieves preface text instead of the sutra.

* **Over-embedded** — chunks run PAST the juan into later ones, because the old
  parse lumped several juan into one text_contents row and every chunk was
  stamped with the FIRST juan's number. Symptom (prod, 2026-07-28): a user asked
  a 俱舍論 question; (text 38, juan 13) holds 109 chunks spanning real juan
  13→17, so RAG served a 卷16 passage under the header `[出处: 《阿毘達磨俱舍
  論》第13卷]`. The quote was verbatim-correct and the fascicle was wrong — the
  worst shape for a scholarly tool, because every downstream guard trusts
  juan_num. citation_guard whitelists it, quote_verifier finds the quote in the
  chunk, and the reader drawer renders it under the wrong 卷 heading.

This pass originally looked only for the under-embedded side, so the
over-embedded juans were structurally invisible to it and never repaired. The
prod census when that was found: 1,020 juans across 561 texts over-embedded, 0
under-embedded (the under side had already been cleaned up by earlier runs).

What this does
--------------
Finds every (text_id, juan_num) of an lzh (Chinese-canon) text whose embedded
character total is < RATIO of, or > OVER_RATIO of, its current lzh text_contents
length, then for each such juan: recomputes embeddings from the CURRENT content
and atomically replaces the juan's rows (DELETE + INSERT in one short
transaction, embeddings computed first so the row-lock window stays tiny).

Correct chunking (chunk_size=500, overlap=50 → stride 450) embeds a juan to
~500/450 = 1.11x its content, so OVER_RATIO must stay clear of that; 1.3 leaves
margin without missing real spills, which run 2x–58x.

`--min-content` is load-bearing on the over side: prod has juans whose
text_contents is a stub of a few dozen chars (閑居編 X0949 etc.) against normal
embeddings. There the CONTENT is broken, not the vectors, and re-embedding would
delete real chunks and write back almost nothing. The length filter is the only
thing preventing that data loss — never lower it to chase a big ratio.

Idempotent & resumable: it commits per juan and the candidate set is recomputed
from the live ratio, so a re-run after an interruption skips already-fixed juans.
Re-embedding a healthy juan is harmless (same model BAAI/bge-m3, same content =>
same vectors), so the thresholds only need to avoid missing broken juans.

Usage (inside the fojin-backend container, DB + embedding API reachable):
    python scripts/repair_stale_embeddings.py --dry-run
    python scripts/repair_stale_embeddings.py
    python scripts/repair_stale_embeddings.py --ratio 0.9 --over-ratio 1.3 --min-content 500
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


async def _find_candidates(conn, ratio: float, min_content: int, over_ratio: float):
    """(text_id, juan_num, content_chars, embedded_chars) needing repair.

    Two-sided on purpose — see the module docstring. `e < ratio * c` catches a
    juan embedded from a truncated parse; `e > over_ratio * c` catches one whose
    chunks spill into later juan under this juan's number. Both mean the vectors
    do not describe the juan they are filed under.
    """
    rows = (
        await conn.execute(
            sql_text(
                """
                WITH emb AS (
                    SELECT text_id, juan_num, sum(length(chunk_text)) AS e
                    FROM text_embeddings GROUP BY text_id, juan_num
                ),
                con AS (
                    SELECT tc.text_id, tc.juan_num, tc.content, length(tc.content) AS c
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
                   OR (
                        COALESCE(emb.e, 0) > CAST(:over_ratio AS double precision) * con.c
                        -- Ratio alone is only a proxy and it over-selects badly:
                        -- on prod it flagged 1,881 juans where just 1,020 had
                        -- actually spilled. The other 861 are simply chunked at a
                        -- denser stride — every chunk still inside its own juan,
                        -- self-consistent, and their alignment_pairs /
                        -- mitra_alignments rows point at that scheme. Re-embedding
                        -- them renumbers chunk_index and breaks those references
                        -- for texts that were never broken, so the ratio is used
                        -- only as a cheap prefilter and the actual test is
                        -- containment: does the LAST chunk still live in this
                        -- juan's text? Chunks are sequential, so if the furthest
                        -- one is inside, nothing ran past the end.
                        AND EXISTS (
                            SELECT 1 FROM text_embeddings te
                            WHERE te.text_id = con.text_id
                              AND te.juan_num = con.juan_num
                              AND te.chunk_index = (
                                  SELECT max(t2.chunk_index) FROM text_embeddings t2
                                  WHERE t2.text_id = con.text_id
                                    AND t2.juan_num = con.juan_num
                              )
                              -- Short tail chunk: a <40-char needle matches too
                              -- easily, so treat it as "can't tell" and leave the
                              -- juan alone rather than risk a needless re-embed.
                              AND length(trim(te.chunk_text)) >= 40
                              -- LIKE (not position/instr) to stay runnable on both
                              -- postgres and the sqlite used by the tests. CBETA
                              -- bodies carry no percent, underscore or backslash,
                              -- so no LIKE escaping is needed.
                              AND con.content NOT LIKE
                                  '%' || substr(trim(te.chunk_text), 1, 40) || '%'
                        )
                   )
                ORDER BY con.text_id, con.juan_num
                """
            ),
            {"ratio": ratio, "over_ratio": over_ratio, "minc": min_content},
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
    ap.add_argument("--over-ratio", type=float, default=1.3,
                    help="repair juans whose embedded chars > over_ratio * content chars "
                         "(chunks spilling into later juan). Healthy chunking lands at "
                         "~1.11 from the 500/450 overlap stride — keep clear of it.")
    ap.add_argument("--min-content", type=int, default=500,
                    help="only consider lzh juans with content longer than this; also "
                         "shields juans whose text_contents is a stub from being "
                         "re-embedded down to nothing")
    ap.add_argument("--dry-run", action="store_true", help="report scope, write nothing")
    ap.add_argument("--limit", type=int, default=0, help="cap juans processed (0 = all)")
    args = ap.parse_args()

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    t0 = time.time()
    done = chunks_total = 0
    failed: list[tuple[int, int]] = []
    try:
        async with engine.connect() as conn:
            cands = await _find_candidates(
                conn, args.ratio, args.min_content, args.over_ratio
            )
            await conn.rollback()  # close the read tx auto-begun by the candidate query
            # Split the two sides: summing (c - e) over both would net a spilled
            # juan's surplus against a truncated one's deficit and report a
            # meaningless — often negative — "missing chars" total.
            under = [x for x in cands if x[3] < args.ratio * x[2]]
            over = [x for x in cands if x[3] > args.over_ratio * x[2]]
            repaired_text_ids: set[int] = set()
            print(
                f"candidates: {len(cands)} juans across "
                f"{len({t for t, _, _, _ in cands})} texts "
                f"(ratio<{args.ratio} min_content>{args.min_content} "
                f"over_ratio>{args.over_ratio})\n"
                f"  under-embedded: {len(under)} juans, "
                f"~{sum(c - e for _, _, c, e in under):,} missing chars\n"
                f"  over-embedded:  {len(over)} juans, "
                f"~{sum(e - c for _, _, c, e in over):,} surplus chars "
                f"(chunks spilling into later juan)",
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
