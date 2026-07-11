"""Backfill mitra_alignments.mitra_e_score with a BGE-M3 cosine PROXY score.

*** THIS IS A PROXY SCORE, NOT THE REAL MITRA-E GATE. ***

The score written here is the cosine similarity between the BGE-M3 embeddings
of `zh_text` and `foreign_text` (multilingual bi-encoder, the platform's
standard embedding model — see app/services/embedding.py). The MITRA project's
own quality gate is MITRA-E (9B), a dedicated semantic filter that needs ~36 GB
of GPU memory and runs offline; until that backfill happens, this proxy is the
only per-pair quality signal. Consequences:

- The column name is mitra_e_score for forward compatibility, but values
  written by THIS script are BGE-M3 cosines in roughly [0, 1].
- Thresholds MUST be calibrated against human labels before any read path
  filters on this column (the anticipated `WHERE mitra_e_score >= 0.30` in
  api/alignment.py is a placeholder, not a calibrated cutoff). Use
  --export-calibration to draw a stratified sample for labeling.

Design (mirrors scripts/import_mitra_alignments.py):
- One dedicated NullPool connection for the whole run (see the 2026-06-14
  connection-pool incident in docs/mitra-alignment-integration.md).
- Resumable: processes `WHERE mitra_e_score IS NULL` in id order with a
  keyset cursor; killing and restarting the script continues where it left
  off. Rows skipped due to embedding failures stay NULL and are retried on
  the next run.
- Batched: `--batch-size` rows per iteration; each batch is ONE embeddings
  API call (2 x batch texts) and one executemany UPDATE + commit.
- Embedding-API failures are retried a few times with backoff, then the
  batch is skipped (counted, cursor advances) so one bad batch cannot stall
  a 900K-row run.

Usage (inside backend container, DB + embedding API reachable):
    python scripts/backfill_mitra_scores.py --limit 1000 --dry-run
    python scripts/backfill_mitra_scores.py --batch-size 64
    python scripts/backfill_mitra_scores.py --export-calibration 500 /tmp/calib.jsonl

--dry-run embeds and scores (so it exercises the real pipeline and prints the
score distribution) but performs no writes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections.abc import Iterable, Iterator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.exceptions import EmbeddingServiceError
from app.services import embedding as embedding_service

BANDS = 10  # calibration-export score deciles over [0, 1]

FETCH = sql_text(
    """
    SELECT id, zh_text, foreign_text
    FROM mitra_alignments
    WHERE mitra_e_score IS NULL AND id > :cursor
    ORDER BY id
    LIMIT :n
    """
)

UPDATE = sql_text("UPDATE mitra_alignments SET mitra_e_score = :score WHERE id = :id")


# ---------------------------------------------------------------------------
# Pure logic (unit-tested in tests/test_backfill_mitra_scores.py)
# ---------------------------------------------------------------------------


def cosine_similarity(a: list[float], b: list[float]) -> float | None:
    """Cosine similarity of two vectors, clamped to [-1, 1].

    Returns None for zero-norm or mismatched-length vectors (score cannot be
    computed; the row is skipped and stays NULL).
    """
    if not a or not b or len(a) != len(b):
        return None
    dot = na = nb = 0.0
    for x, y in zip(a, b, strict=True):  # lengths validated above
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return None
    return max(-1.0, min(1.0, dot / math.sqrt(na * nb)))


def chunked(items: Iterable, size: int) -> Iterator[list]:
    """Yield consecutive lists of at most `size` items."""
    if size < 1:
        raise ValueError("size must be >= 1")
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def band_of(score: float, bands: int = BANDS) -> int:
    """Map a score to a decile band index in [0, bands-1], clamping outliers.

    Band i covers [i/bands, (i+1)/bands); the last band is closed at 1.0 so a
    perfect cosine lands in band bands-1, and float fuzz / negatives clamp to
    the edge bands instead of raising.
    """
    return min(bands - 1, max(0, int(score * bands)))


def allocate_quotas(total: int, available: list[int]) -> list[int]:
    """Spread `total` sample slots across bands with `available[i]` rows each.

    Starts from an even split (remainder goes to the earliest bands), caps each
    band at what it actually has, then redistributes the shortfall round-robin
    to bands with spare rows. Deterministic. If sum(available) < total, every
    band is simply taken in full.
    """
    n = len(available)
    if n == 0 or total <= 0:
        return [0] * n
    if sum(available) <= total:
        return list(available)
    base, rem = divmod(total, n)
    quotas = [min(available[i], base + (1 if i < rem else 0)) for i in range(n)]
    deficit = total - sum(quotas)
    while deficit > 0:
        progressed = False
        for i in range(n):
            if deficit == 0:
                break
            if quotas[i] < available[i]:
                quotas[i] += 1
                deficit -= 1
                progressed = True
        if not progressed:  # pragma: no cover - unreachable (sum(available) > total)
            break
    return quotas


# ---------------------------------------------------------------------------
# Embedding with small retry, then skip
# ---------------------------------------------------------------------------


async def embed_with_retry(
    texts: list[str],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    embed_fn=None,
) -> list[list[float]] | None:
    """Call the batch embeddings API with `attempts` tries and linear backoff.

    Returns None once all attempts fail (caller skips the batch and counts it).
    `embed_fn` is injectable for tests; defaults to the platform client.
    """
    if embed_fn is None:
        embed_fn = embedding_service.generate_embeddings_batch
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await embed_fn(texts)
        except EmbeddingServiceError as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(base_delay * attempt)
    print(f"  embedding failed after {attempts} attempts: {last_error}")
    return None


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


async def run_backfill(
    conn,
    *,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    log_every: int,
    retry_attempts: int,
    retry_delay: float,
) -> tuple[int, int]:
    """Score NULL rows in id order. Returns (scored, skipped)."""
    remaining = (
        await conn.execute(sql_text("SELECT count(*) FROM mitra_alignments WHERE mitra_e_score IS NULL"))
    ).scalar_one()
    target = remaining if limit is None else min(limit, remaining)
    print(f"unscored rows: {remaining}; this run targets {target}; dry_run={dry_run}")

    cursor = 0
    scored = skipped = 0
    hist = [0] * BANDS
    t0 = time.time()
    last_logged = 0

    while scored + skipped < target:
        n = min(batch_size, target - scored - skipped)
        rows = (await conn.execute(FETCH, {"cursor": cursor, "n": n})).fetchall()
        if not rows:
            break
        cursor = rows[-1][0]

        # One API call embeds both sides: [zh_0..zh_B-1, fo_0..fo_B-1].
        inputs = [r[1] for r in rows] + [r[2] for r in rows]
        vectors = await embed_with_retry(inputs, attempts=retry_attempts, base_delay=retry_delay)
        if vectors is None or len(vectors) != len(inputs):
            skipped += len(rows)
            print(f"  skipped batch of {len(rows)} (ids <= {cursor}): embedding unavailable")
            continue

        updates: list[dict] = []
        for i, row in enumerate(rows):
            score = cosine_similarity(vectors[i], vectors[len(rows) + i])
            if score is None:
                skipped += 1
                continue
            hist[band_of(score)] += 1
            updates.append({"id": row[0], "score": score})

        if updates and not dry_run:
            await conn.execute(UPDATE, updates)
            await conn.commit()
        scored += len(updates)

        done = scored + skipped
        if done - last_logged >= log_every or done >= target:
            last_logged = done
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (target - done) / rate if rate > 0 else float("inf")
            print(
                f"progress: {done}/{target} ({done * 100 // max(target, 1)}%) "
                f"scored={scored} skipped={skipped} "
                f"rate={rate:.1f} rows/s eta={eta:.0f}s"
            )

    print("score distribution (proxy BGE-M3 cosine):")
    for i, count in enumerate(hist):
        lo, hi = i / BANDS, (i + 1) / BANDS
        print(f"  [{lo:.1f}, {hi:.1f}{']' if i == BANDS - 1 else ')'}: {count}")
    return scored, skipped


# ---------------------------------------------------------------------------
# Calibration export
# ---------------------------------------------------------------------------


async def run_export(conn, n: int, path: str) -> int:
    """Export a stratified JSONL sample of scored rows for human labeling.

    Spreads n rows across the 10 score-decile bands (edge bands are open-ended
    so clamped outliers are included) so the labeled set covers the whole
    quality range instead of just the bulk of the distribution.
    """
    available: list[int] = []
    for i in range(BANDS):
        lo, hi = i / BANDS, (i + 1) / BANDS
        where = _band_where(i, BANDS)
        count = (
            await conn.execute(
                sql_text(f"SELECT count(*) FROM mitra_alignments WHERE {where}"),  # nosec B608 - static band SQL
                {"lo": lo, "hi": hi},
            )
        ).scalar_one()
        available.append(count)

    quotas = allocate_quotas(n, available)
    print(f"band availability: {available}")
    print(f"band quotas:       {quotas}")

    written = 0
    with open(path, "w", encoding="utf-8") as fh:
        for i, quota in enumerate(quotas):
            if quota == 0:
                continue
            lo, hi = i / BANDS, (i + 1) / BANDS
            where = _band_where(i, BANDS)
            rows = (
                await conn.execute(
                    sql_text(
                        "SELECT id, taisho_id, zh_text, foreign_text, foreign_lang, mitra_e_score "
                        f"FROM mitra_alignments WHERE {where} "  # nosec B608 - static band SQL
                        "ORDER BY random() LIMIT :quota"
                    ),
                    {"lo": lo, "hi": hi, "quota": quota},
                )
            ).fetchall()
            for row in rows:
                fh.write(
                    json.dumps(
                        {
                            "id": row[0],
                            "taisho_id": row[1],
                            "zh_text": row[2],
                            "foreign_text": row[3],
                            "foreign_lang": row[4],
                            "mitra_e_score": row[5],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
    print(f"wrote {written} rows to {path}")
    return written


def _band_where(i: int, bands: int = BANDS) -> str:
    """WHERE clause for band i. Edge bands are open-ended so out-of-range
    scores (float fuzz below 0 / at exactly 1.0) still fall in a band."""
    if i == 0:
        return "mitra_e_score IS NOT NULL AND mitra_e_score < :hi"
    if i == bands - 1:
        return "mitra_e_score >= :lo"
    return "mitra_e_score >= :lo AND mitra_e_score < :hi"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch-size", type=int, default=64, help="rows per embed+write batch (default 64)")
    ap.add_argument("--limit", type=int, default=None, help="max rows to process this run")
    ap.add_argument("--dry-run", action="store_true", help="embed + score + report, no writes")
    ap.add_argument("--log-every", type=int, default=5000, help="log progress every N rows (default 5000)")
    ap.add_argument("--retry-attempts", type=int, default=3, help="embedding API attempts per batch (default 3)")
    ap.add_argument(
        "--export-calibration",
        nargs=2,
        metavar=("N", "PATH"),
        help="export a stratified sample of N scored rows to PATH (JSONL) and exit",
    )
    return ap


async def main() -> int:
    args = _build_parser().parse_args()

    if args.batch_size < 1:
        print("ERROR: --batch-size must be >= 1")
        return 1

    # Dedicated NullPool engine + one held connection, same rationale as
    # import_mitra_alignments.py (connection-starved prod Postgres).
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            if args.export_calibration:
                n_str, path = args.export_calibration
                n = int(n_str)
                if n < 1:
                    print("ERROR: --export-calibration N must be >= 1")
                    return 1
                await run_export(conn, n, path)
                return 0

            t0 = time.time()
            scored, skipped = await run_backfill(
                conn,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
                log_every=args.log_every,
                retry_attempts=args.retry_attempts,
                retry_delay=2.0,
            )
            print(f"DONE: scored={scored} skipped={skipped} in {time.time() - t0:.1f}s")
            return 0 if skipped == 0 else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
