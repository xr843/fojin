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

# Anchor-expansion deltas: chunk offsets on BOTH sides of a known-aligned pair.
# Alignment has strong locality — consecutive passages in two parallel texts
# align consecutively — so a confirmed pair's neighbours are high-prior
# candidates. This is both faster (index lookups + one distance each, no kNN
# scan) and far more precise than a blind cross-lingual kNN, whose ~0.6 hits are
# mostly spurious (a Chan 語錄 "matching" a Kangyur text). Grows the moat
# outward from its own verified edges.
_ANCHOR_DELTAS = (1, -1, 2, -2)


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


def propose_anchor_neighbour(
    a: ChunkRef, b: ChunkRef, delta: int
) -> tuple[ChunkRef, ChunkRef] | None:
    """From a known-aligned pair (a↔b), propose the pair ``delta`` chunks away on
    both sides — the alignment-locality candidate. Returns None if either side
    would go before chunk 0."""
    if a.chunk_index + delta < 0 or b.chunk_index + delta < 0:
        return None
    return (
        ChunkRef(a.text_id, a.juan_num, a.chunk_index + delta, a.lang),
        ChunkRef(b.text_id, b.juan_num, b.chunk_index + delta, b.lang),
    )


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

    # Cross-lingual kNN can't use the HNSW index: an lzh chunk's nearest
    # neighbours are overwhelmingly other lzh chunks (same-language dominance),
    # so an index scan's top-ef_search candidates contain no pi/bo/sa and the
    # lang filter returns nothing. Force a sequential scan of the target-language
    # subset — correct (all distances computed), but O(target rows) per source
    # chunk (~1min over 246K), so this is an OFFLINE/cron miner, not on-demand.
    # (SCALE follow-up: a per-language embedding index would make this fast.)
    # Fetched the source embedding above WITH indexes on; disable them only now
    # so that lookup stayed fast.
    await raw.exec_driver_sql("SET LOCAL enable_indexscan = off")
    await raw.exec_driver_sql("SET LOCAL enable_bitmapscan = off")
    await raw.exec_driver_sql("SET LOCAL statement_timeout = 120000")
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


async def _pair_similarity(db: AsyncSession, a: ChunkRef, b: ChunkRef) -> float | None:
    """Cosine similarity between two specific chunks, or None if either has no
    embedding. Cheap (two PK lookups + one distance) — no scan."""
    row = (await db.execute(
        text(
            "SELECT 1 - (e1.embedding <=> e2.embedding) "
            "FROM text_embeddings e1, text_embeddings e2 "
            "WHERE e1.text_id = :at AND e1.juan_num = :aj AND e1.chunk_index = :ac "
            "  AND e2.text_id = :bt AND e2.juan_num = :bj AND e2.chunk_index = :bc "
            "  AND e1.embedding IS NOT NULL AND e2.embedding IS NOT NULL"
        ),
        {"at": a.text_id, "aj": a.juan_num, "ac": a.chunk_index,
         "bt": b.text_id, "bj": b.juan_num, "bc": b.chunk_index},
    )).first()
    return float(row[0]) if row else None


async def mine_from_anchors(
    db: AsyncSession,
    *,
    limit: int = 200,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    deltas: tuple[int, ...] = _ANCHOR_DELTAS,
) -> int:
    """Grow the moat outward from its verified edges: for each known-aligned pair
    (anchor), propose the neighbouring chunk pairs (±delta on both sides) and
    stage those above ``threshold`` that aren't already known.

    Far better precision than the blind cross-lingual kNN (alignment locality),
    and fast — each candidate is two PK lookups + one distance, no 246K-row scan.
    Best-effort per anchor; returns total staged."""
    anchors = (await db.execute(
        text(
            "SELECT text_a_id, text_a_juan_num, text_a_chunk_index, text_a_lang, "
            "       text_b_id, text_b_juan_num, text_b_chunk_index, text_b_lang "
            "FROM alignment_pairs "
            "WHERE text_a_id IS NOT NULL AND text_b_id IS NOT NULL "
            "  AND text_a_chunk_index IS NOT NULL AND text_b_chunk_index IS NOT NULL "
            "LIMIT :limit"
        ),
        {"limit": limit},
    )).all()

    total = 0
    for r in anchors:
        a = ChunkRef(text_id=r[0], juan_num=r[1], chunk_index=r[2], lang=r[3] or "lzh")
        b = ChunkRef(text_id=r[4], juan_num=r[5], chunk_index=r[6], lang=r[7] or "lzh")
        for delta in deltas:
            prop = propose_anchor_neighbour(a, b, delta)
            if prop is None:
                continue
            na, nb = prop
            try:
                sim = await _pair_similarity(db, na, nb)
                if sim is None:
                    continue
                existing = await _existing_pair_keys(db, na)
                triples = select_new_candidates(na, [(nb, sim)], existing, threshold=threshold)
                total += await stage_candidates(db, na, triples, source_name="anchor-expansion")
            except Exception:
                logger.warning("mine_from_anchors failed for %s->%s", na, nb, exc_info=True)
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
