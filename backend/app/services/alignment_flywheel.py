"""Cross-canon alignment flywheel — mine candidates, stage, human-review, promote.

The moat (verified cross-canon alignment) grows through a pipeline, not a bulk
import:

  1. **mine** (cheap, high-recall): for source-language chunks, find the nearest
     cross-language chunk by embedding cosine similarity (fojin embeds all langs
     in one space, so lzh↔pi↔bo nearest-neighbour is meaningful). Stage those
     above a threshold — that aren't already aligned — as *pending* candidates.
  2. **review** (human, high-precision): an admin accepts or rejects each.
  3. **promote**: an accepted candidate is written into ``alignment_pairs`` —
     the table RAG and the reader trust as ground truth. A bad automatic match
     therefore never becomes a served "parallel" without a human in the loop.

This module keeps the *decision* logic pure (threshold + dedup) and unit-tested;
the kNN mine needs the corpus DB + pgvector and runs on prod/cron like the eval.
This is slice 1 — candidate generation + review + promote. Later slices add
LLM pre-verification, batch review UX, and provenance/quality scoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alignment_candidate import AlignmentCandidate

logger = logging.getLogger(__name__)

# Default cosine-similarity floor for a chunk pair to be worth a human's time.
# CROSS-lingual similarity (lzh↔pi, different scripts in one embedding space)
# runs lower than intra-lingual, so this is lower than a same-language search
# would use. The miner is high-recall; review is the precision stage. Tunable
# per run.
DEFAULT_SIMILARITY_THRESHOLD = 0.5
# Cross-canon target languages a source (lzh) chunk is matched against.
DEFAULT_TARGET_LANGS = ("pi", "bo", "sa")


@dataclass(frozen=True)
class ChunkRef:
    """A retrieved chunk keyed the same way as alignment_pairs."""
    text_id: int
    juan_num: int
    chunk_index: int
    lang: str


def pair_key(a: ChunkRef, b: ChunkRef) -> tuple:
    """Directed dedup key for a candidate pair (source a → target b)."""
    return (a.text_id, a.juan_num, a.chunk_index, b.text_id, b.juan_num, b.chunk_index)


def select_new_candidates(
    source: ChunkRef,
    neighbours: list[tuple[ChunkRef, float]],
    existing_keys: set[tuple],
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[tuple[ChunkRef, ChunkRef, float]]:
    """Pure decision step: from a source chunk's cross-language neighbours, pick
    the (source, target, similarity) triples worth staging.

    A neighbour is kept iff its similarity ≥ threshold, it's a different text,
    and the directed pair isn't already known (in alignment_pairs *or* already
    staged — the caller passes both in ``existing_keys``). Within one call the
    same target is de-duplicated too."""
    out: list[tuple[ChunkRef, ChunkRef, float]] = []
    seen: set[tuple] = set()
    for target, sim in neighbours:
        if sim < threshold:
            continue
        if target.text_id == source.text_id:
            continue
        key = pair_key(source, target)
        if key in existing_keys or key in seen:
            continue
        seen.add(key)
        out.append((source, target, sim))
    return out


async def _existing_pair_keys(db: AsyncSession, source: ChunkRef) -> set[tuple]:
    """Directed keys already known for this source chunk — from the ground-truth
    ``alignment_pairs`` (either direction) and from prior candidates — so the
    miner never re-stages a pair."""
    keys: set[tuple] = set()
    rows = (await db.execute(
        text(
            "SELECT text_b_id, text_b_juan_num, text_b_chunk_index "
            "FROM alignment_pairs "
            "WHERE text_a_id = :tid AND text_a_juan_num = :juan AND text_a_chunk_index = :cidx"
        ),
        {"tid": source.text_id, "juan": source.juan_num, "cidx": source.chunk_index},
    )).all()
    for r in rows:
        if r[0] is not None:
            keys.add((source.text_id, source.juan_num, source.chunk_index, r[0], r[1], r[2]))
    prior = (await db.execute(
        select(
            AlignmentCandidate.text_b_id,
            AlignmentCandidate.text_b_juan_num,
            AlignmentCandidate.text_b_chunk_index,
        ).where(
            AlignmentCandidate.text_a_id == source.text_id,
            AlignmentCandidate.text_a_juan_num == source.juan_num,
            AlignmentCandidate.text_a_chunk_index == source.chunk_index,
        )
    )).all()
    for r in prior:
        keys.add((source.text_id, source.juan_num, source.chunk_index, r[0], r[1], r[2]))
    return keys


async def stage_candidates(
    db: AsyncSession,
    source: ChunkRef,
    triples: list[tuple[ChunkRef, ChunkRef, float]],
    *,
    source_name: str = "knn-bootstrap",
) -> int:
    """Insert new candidate rows (pending). Returns how many were added.

    Skips any pair already known for this source (defence in depth over the
    unique index). Commit is the caller's."""
    if not triples:
        return 0
    existing = await _existing_pair_keys(db, source)
    added = 0
    for a, b, sim in triples:
        if pair_key(a, b) in existing:
            continue
        db.add(AlignmentCandidate(
            text_a_id=a.text_id, text_a_juan_num=a.juan_num,
            text_a_chunk_index=a.chunk_index, text_a_lang=a.lang,
            text_b_id=b.text_id, text_b_juan_num=b.juan_num,
            text_b_chunk_index=b.chunk_index, text_b_lang=b.lang,
            similarity=round(float(sim), 4), source=source_name, status="pending",
        ))
        added += 1
    return added


async def _cross_lang_neighbours(
    db: AsyncSession, source: ChunkRef, target_langs: tuple[str, ...], k: int
) -> list[tuple[ChunkRef, float]]:
    """Top-k nearest cross-language chunks to ``source`` by embedding cosine
    similarity (pgvector). fojin embeds all languages in one space, so this is a
    meaningful lzh↔pi↔bo match.

    Perf: the source embedding is fetched once and passed as a literal (mirroring
    ``embedding.similarity_search``), not a correlated ``(SELECT … FROM src)``
    subquery — the subquery form made the planner re-evaluate per row and blow
    the statement timeout on prod. The mine also raises the per-statement timeout
    since a filtered cross-lingual scan is heavier than a normal query."""
    lang_list = ",".join(f"'{lg}'" for lg in target_langs if lg.isalpha())  # nosec B608 — whitelist langs
    raw = await db.connection()

    src = (await raw.exec_driver_sql(
        "SELECT embedding FROM text_embeddings "
        "WHERE text_id = $1 AND juan_num = $2 AND chunk_index = $3",
        (source.text_id, source.juan_num, source.chunk_index),
    )).first()
    if not src or src[0] is None:
        return []
    emb = src[0]  # asyncpg returns the pgvector column as a '[...]' string

    # A filtered cross-lingual kNN scans more than a normal query; give it room
    # so it isn't cancelled by the default statement_timeout (SET LOCAL scopes it
    # to this transaction only).
    await raw.exec_driver_sql("SET LOCAL statement_timeout = 25000")
    rows = (await raw.exec_driver_sql(
        "SELECT te.text_id, te.juan_num, te.chunk_index, bt.lang, "
        "       1 - (te.embedding <=> $1::vector) AS sim "
        "FROM text_embeddings te JOIN buddhist_texts bt ON bt.id = te.text_id "
        f"WHERE bt.lang IN ({lang_list}) AND te.embedding IS NOT NULL "
        "ORDER BY te.embedding <=> $1::vector "
        "LIMIT $2",
        (emb, k),
    )).all()
    return [
        (ChunkRef(text_id=r[0], juan_num=r[1], chunk_index=r[2], lang=r[3] or "lzh"), float(r[4]))
        for r in rows
    ]


async def mine_candidates(
    db: AsyncSession,
    *,
    limit: int = 200,
    per_source_k: int = 3,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    target_langs: tuple[str, ...] = DEFAULT_TARGET_LANGS,
    source_lang: str = "lzh",
) -> int:
    """Mine cross-canon candidates for a bounded batch of source-language chunks.

    Needs the corpus DB + pgvector (run on prod/cron). For up to ``limit`` source
    chunks, finds their nearest target-language chunks, stages new ones above
    ``threshold``. Returns total staged. Best-effort per source — one failure is
    logged and skipped, not fatal."""
    source_rows = (await db.execute(
        text(
            "SELECT te.text_id, te.juan_num, te.chunk_index "
            "FROM text_embeddings te JOIN buddhist_texts bt ON bt.id = te.text_id "
            "WHERE bt.lang = :lang AND te.embedding IS NOT NULL "
            "ORDER BY te.text_id, te.juan_num, te.chunk_index "
            "LIMIT :limit"
        ),
        {"lang": source_lang, "limit": limit},
    )).all()

    total = 0
    for sr in source_rows:
        source = ChunkRef(text_id=sr[0], juan_num=sr[1], chunk_index=sr[2], lang=source_lang)
        try:
            neighbours = await _cross_lang_neighbours(db, source, target_langs, per_source_k)
            existing = await _existing_pair_keys(db, source)
            triples = select_new_candidates(source, neighbours, existing, threshold=threshold)
            total += await stage_candidates(db, source, triples)
        except Exception:
            logger.warning("mine_candidates failed for %s", source, exc_info=True)
    await db.commit()
    return total


async def list_pending(db: AsyncSession, limit: int = 50) -> list[AlignmentCandidate]:
    """Highest-similarity pending candidates first — review the most promising."""
    rows = await db.execute(
        select(AlignmentCandidate)
        .where(AlignmentCandidate.status == "pending")
        .order_by(AlignmentCandidate.similarity.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def _promote_to_alignment_pairs(db: AsyncSession, c: AlignmentCandidate) -> None:
    """Write an accepted candidate into the ground-truth alignment_pairs table."""
    await db.execute(
        text(
            "INSERT INTO alignment_pairs "
            "(text_a_id, text_a_juan_num, text_a_chunk_index, text_a_lang, "
            " text_b_id, text_b_juan_num, text_b_chunk_index, text_b_lang, "
            " confidence, method) "
            "VALUES (:ta, :taj, :tac, :tal, :tb, :tbj, :tbc, :tbl, :conf, 'flywheel-verified')"
        ),
        {
            "ta": c.text_a_id, "taj": c.text_a_juan_num, "tac": c.text_a_chunk_index, "tal": c.text_a_lang,
            "tb": c.text_b_id, "tbj": c.text_b_juan_num, "tbc": c.text_b_chunk_index, "tbl": c.text_b_lang,
            "conf": c.similarity,
        },
    )


async def review_candidate(
    db: AsyncSession, candidate_id: int, *, accept: bool, user_id: int | None
) -> AlignmentCandidate | None:
    """Accept (→ promote into alignment_pairs) or reject a pending candidate.

    Idempotent-ish: a candidate already reviewed is returned unchanged (no
    double-promote). Returns None if the id doesn't exist. Commit is the
    caller's."""
    c = (await db.execute(
        select(AlignmentCandidate).where(AlignmentCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if c is None or c.status != "pending":
        return c
    if accept:
        await _promote_to_alignment_pairs(db, c)
        c.status = "accepted"
    else:
        c.status = "rejected"
    c.reviewed_at = datetime.now(UTC)
    c.reviewed_by = user_id
    return c
