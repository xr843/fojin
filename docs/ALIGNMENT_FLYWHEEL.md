# Cross-canon alignment flywheel

fojin's moat is **verified cross-canon alignment** — but it sits at only ~3K
chunk pairs. Growing it safely means a pipeline, not a bulk import, so a bad
automatic match never becomes a served "parallel" without a human in the loop.

```
mine (cheap, high-recall)  →  review (human, high-precision)  →  promote
   pgvector kNN                admin accept / reject             alignment_pairs
   → alignment_candidates                                        (ground truth)
```

This is **slice 1**: candidate generation + review + promote. Later slices:
LLM pre-verification (auto-reject obvious mismatches before a human sees them),
batch review UX, provenance/quality scoring, bootstrap from BuddhaNexus / MITRA
open alignment output.

## 1. Mine (prod / cron — needs the corpus DB + pgvector)

Two strategies, in order of preference:

**`mine_from_anchors` (preferred — precise + fast).** Grows the moat outward
from its verified edges: for each known-aligned pair, propose the neighbouring
chunk pairs (±1, ±2 on both sides — alignment has strong locality) and stage the
ones above threshold. Each candidate is two PK lookups + one distance (no scan),
and precision is high because the prior is a confirmed alignment — unlike the
blind kNN below, whose ~0.6 cross-lingual hits are mostly spurious (a Chan 語錄
"matching" a Kangyur text).

```python
from app.services.alignment_flywheel import mine_from_anchors
n = await mine_from_anchors(db, limit=500, threshold=0.5)
```

**`mine_candidates` (blind cross-lingual kNN — high recall, low precision, slow).**
For source-language chunks with no aligned neighbour to expand from. Correct but
~60s/chunk (same-language dominance forces a sequential scan of the 246K target
embeddings — HNSW returns nothing useful), so offline only. Scale/precision
follow-up: a per-language embedding index + LLM pre-verification of candidates.


`app.services.alignment_flywheel.mine_candidates` embeds each source-language
(default `lzh`) chunk against the cross-canon target languages (`pi`/`bo`/`sa`)
in fojin's shared embedding space, and stages new pairs above a similarity
threshold that aren't already in `alignment_pairs`.

```bash
# inside the backend container, cwd /app
docker compose exec -T backend python - <<'PY'
import asyncio
from app.database import async_session
from app.services.alignment_flywheel import mine_candidates
async def main():
    async with async_session() as db:
        n = await mine_candidates(db, limit=500, threshold=0.62)
        print("staged", n, "candidates")
asyncio.run(main())
PY
```

Bounded per run (`limit` source chunks); re-runnable — it skips pairs already
staged or aligned. Good cron cadence: a modest `limit` nightly so the review
queue never floods.

## 2. Review (admin API)

```
GET  /api/admin/alignment-candidates?limit=50      # pending, highest-similarity first
POST /api/admin/alignment-candidates/{id}/review   # body: {"accept": true|false}
```

Accept promotes the pair into `alignment_pairs` with `method='flywheel-verified'`
and `confidence` = the mined similarity; reject just marks it. Both are
idempotent (an already-reviewed candidate is a no-op, so no double-promote).

## 3. Effect

Every accepted candidate immediately widens what the trilingual RAG and the
reader's 多语对读 panel can surface — the moat grows one verified pair at a
time, and the `/admin/alignment-coverage` dashboard (PR #895) shows where the
biggest gaps still are, to steer the next mine.
```
