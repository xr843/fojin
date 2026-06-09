# Cross-Canon Alignment — Batch 2 Roadmap

Date: 2026-06-09  
Status: Draft planning (no code yet)  
Owner: xr843  
Prior batches:
- Batch 1 (2026-06-08): Lotus Sutra `lotus_zh_bo` — 259 pairs, $1.70
- Batch 1.5 (2026-06-09): 8,000-verse Prajñāpāramitā `prajna_8k_zh_bo` — 127 pairs, $3.64

## Goal

Bring the Mahāyāna 汉藏 corpus to **5 sūtras** by end of June: Lotus + 8k-Prajñāpāramitā done; the remaining three target the central works that any "cross-canon Buddhist text platform" claim has to cover —

1. **大般涅槃經 / Mahāparinirvāṇa-mahāsūtra** (T0374 / Toh 119)
2. **摩訶般若波羅蜜經 / 25,000-verse Prajñāpāramitā** (T0223 / Toh 9)
3. **入楞伽經 / Laṅkāvatāra-sūtra** (T0670 or T0671 / Toh 107)

After Batch 2 the README's "trilingual cross-canon" claim no longer hinges on the original 5-sūtra MVP — it stands on the actual canonical core.

## Constraints uncovered by prior batches

These came out of Batch 1 and 1.5 the hard way; record them up front so Batch 2 doesn't repeat them.

| Constraint | Where it bites | Mitigation already in place |
|---|---|---|
| Single-`text_a` pairs run as one DB transaction | `process_pair` outer loop iterates `a_resolved`; for single-`text_a` pairs the only `commit()` was at end | `--commit-every N` (#659, default 10) |
| `settings.llm_model` defaults to a reasoning model in prod | `deepseek-v4-pro` reasoning_tokens balloon cost beyond `LLM_PRICE_PER_1K` estimate | `REASONING_MODELS_DENYLIST` + `--force-reasoning-model` (#658). Operators set `VERIFY_LLM_MODEL=deepseek-v4-flash` |
| `deploy.sh` cron tick kills `docker exec` scripts | `backend/scripts/*.py` changes triggered backend container recreate | `deploy.sh` filters `scripts/tests/eval/alembic` (#664). Long runs no longer need a marker bump as a workaround |
| DeepSeek strict-JSON mode occasionally returns truncated/empty body | ~6% rate observed during Lotus & Prajna runs; LLM is silently rejected | `llm_verify_pair` catches `JSONDecodeError` → `parse_fail`. Acceptable noise floor |

## Candidate dispatch

Numbers below are from the 2026-06-09 prod probe (`fojin-postgres`, `chunks` column = count of `text_embeddings` rows for that `text_id`).

| Candidate | CBETA | Toh | lzh chunks | bo chunks | Status | Verdict |
|---|---|---|---:|---:|---|---|
| **8k-Prajñāpāramitā** | T0227 | Toh 11 | 193 | 4,706 | **done (Batch 1.5)** | — |
| Lotus | T0262 | Toh 113 | 182 | 1,307 | **done (Batch 1)** | — |
| **25k-Prajñāpāramitā** | T0223 | Toh 9 | 815 | 12,022 | both embedded | **Batch 2a** — needs split |
| **大般涅槃經 (Mahāparinirvāṇa)** | T0374 | Toh 119 | 1,548 | **0** | Toh embedding missing | blocked on 84000 ingest |
| 楞嚴經 (Śūraṅgama) | T0945 | Toh 506 | 176 | **0** | Toh embedding missing | blocked on 84000 ingest |
| 楞伽經 (Laṅkāvatāra) | T0670 / T0671 / T0672 | Toh 107 | 220–307 | (unverified — not in our probe sweep) | needs verification | **Batch 2b** after a probe |
| 大集經 (Mahāsannipāta) | T0397 | (unmapped) | 2,494 | — | Toh number unknown | research first |
| 寶積部 (Ratnakūṭa) | T0310 | Toh 45–93 (multi) | 3,979 | — | multi-Toh, must split by chapter | Batch 3 |

So the actually-shippable Batch 2 targets, today, are **25k-Prajñāpāramitā** (a big one) and **Laṅkāvatāra** (a medium one, pending Toh 107 chunk check). Everything else either blocks on 84000 ingest gaps or needs preliminary research.

### Why not just queue Mahāparinirvāṇa anyway?

Because `Toh 119` has **0 embedded chunks** in our 84000 import. We can't run pgvector recall against a target with no vectors, so the script would resolve text_b OK and then iterate 0 candidates per chunk and exit with `accepted: 0`. Wasted cron time. The pre-req here is **expanding the 84000 ingest to cover the Kangyur sūtra section that includes Toh 119, Toh 506, etc.** — a data-pipeline change, not an alignment-pipeline change. Track separately.

## Batch 2a: 25,000-verse Prajñāpāramitā (T0223 ↔ Toh 9)

This is the headline sūtra of the 般若 corpus and a natural follow-up to Batch 1.5's 8k version. But it's also nearly **5× larger** than anything we've shipped so far.

### Size and cost projection

Using the empirically observed prajna rates (~60–70 s/chunk wall time, $0.011/chunk LLM cost):

| Metric | Lotus | 8k-Prajna | **25k-Prajna (projected)** |
|---|---:|---:|---:|
| lzh chunks (outer loop) | 182 | 193 | **815** |
| Wall time | 2h 45min | 6h 38min (incl. restart) | **~11h** for clean run; ~14h with one restart |
| LLM cost | $1.70 | $3.64 | **~$9** |
| Expected accept rate | 8.6% | 3.4% | **~3–5%** (prajñā style) |
| Expected pairs | 259 | 127 | **~400–500** |

Two problems:
1. **Single SSH session can't reliably hold 11h.** Tailscale check mode requires re-auth at the 12h boundary; in practice anything past ~6h drifts into the danger zone for the SSH-FIFO setup we use.
2. **Single transaction inside `process_pair`'s outer loop would hold 11h.** `--commit-every 10` already addresses this, but at chunk 80 we'd still have 80 commits, which is plenty fine — the DB-side risk is solved.

So the real constraint is operator monitoring, not transaction durability. Two paths to solve it:

### Option A: split by juan (recommended)

T0223 is divided into juans (卷). `fetch_chunks()` already accepts a `juan_filter`. Add a CLI flag `--juans 1,2,3` (or `--juans 1-3`) that narrows the outer loop to a juan slice. Then we run the pair in 3–4 separate cron-tracked sessions over a couple of days. Each session is 2–3h, well within Lotus / 8k-Prajna comfort zone.

Pros:
- Each session has its own log file (`/tmp/prajna25k_juan1.log`, etc.) — easy progress tracking.
- One session crashing doesn't affect the others.
- Pair definition stays a single `prajna_25k_zh_bo` entry; only the runtime invocation differs.
- We get partial coverage immediately: after the first juan ships, that juan is queryable in the reader.

Cons:
- Requires a small change to the script (`--juans` flag + filter pass-through).
- DB queries for `WHERE text_a_id=6 AND text_b_id=5163` will show coverage growing across days — needs operator note in the next ALIGNMENT.md.

### Option B: nohup the run as one long session

Just `nohup docker exec ... &` and walk away. Tail the log every couple of hours. Restart on crash.

Pros: zero code change.  
Cons: a single crash 80% through wastes 8h of LLM spend. And the SSH session abandonment story is iffy on the sg-vps Tailscale check setup.

**Going with A.** Code change is ~30 lines + a CLI test; the operational savings are worth it.

### Implementation sketch

```python
# build_alignments.py — proposed delta
parser.add_argument(
    "--juans",
    default=None,
    help="Restrict text_a chunks to this juan range, e.g. '1,2,3' or '1-3' or '5'. "
         "Useful for splitting a long pair (e.g. T0223 25k-Prajñāpāramitā has 7 juans).",
)
```

`fetch_chunks(session, text_id, juan_filter=...)` already exists in the script — just thread the parsed range through `process_pair`. Idempotency is unchanged: the same `uq_align_chunk_pair` index covers all juans.

### Sequencing

After PR for `--juans` lands:

| Day | Run | Wall time | Cumulative cost |
|---|---|---|---|
| D | T0223 juans 1–2 | ~3h | ~$2.50 |
| D+1 | T0223 juans 3–4 | ~3h | ~$5 |
| D+2 | T0223 juans 5–6 | ~3h | ~$7.50 |
| D+3 | T0223 juan 7 (+ any 残留) | ~1.5h | **~$9 total** |

Each leg uses `--max-spend-usd 5` (the default) — if any single leg approaches that, the ceiling halts it cleanly.

## Batch 2b: Laṅkāvatāra (T0670 / T0671 / T0672 ↔ Toh 107)

The Laṅkāvatāra exists in CBETA in three Chinese translations:

- T0670 (求那跋陀羅, 4 juans, 220 chunks)
- T0671 (菩提流支, 10 juans, 307 chunks)
- T0672 (實叉難陀, 7 juans, 271 chunks)

The Tibetan canonical version is **Toh 107**, but it wasn't in our 2026-06-09 probe sweep. Step zero is:

```sql
SELECT bt.cbeta_id, bt.id, COALESCE(cs.chunks,0) AS chunks
FROM buddhist_texts bt JOIN data_sources ds ON ds.id=bt.source_id
LEFT JOIN (SELECT text_id, COUNT(*) AS chunks FROM text_embeddings GROUP BY text_id) cs ON cs.text_id=bt.id
WHERE bt.cbeta_id = '84K-toh107';
```

If chunks > 0:
- Use **T0671 (菩提流支)** as text_a — it's the standard Chinese version for cross-canon comparison, and 307 chunks gives the richest outer loop without bloating runtime.
- Expected runtime: ~3.5h, expected cost: ~$1.50, expected pairs: ~80 (Laṅkāvatāra is more dialogue-shaped than 般若, so accept rate likely 5–8%).

If chunks == 0: Laṅkāvatāra is blocked on 84000 ingest, same bucket as Mahāparinirvāṇa.

This probe is **the first action** when we open Batch 2 work — costs nothing, settles a ship/block question in seconds.

## Batch 3+ (research, not scheduled)

- **大集經 T0397**: Toh number is non-obvious; the Mahāsannipāta corpus is fragmented in Tibetan canon. Needs a 1-evening Skilling / 84000 catalog read before we commit to a pair definition.
- **寶積部 T0310 → Toh 45–93 series**: 49 sub-assemblies. Right shape for a single pair entry is *not* `prajna_8k`-style single-text — it's a multi-text_b with juan-mapped slicing. Probably better as a Batch 4 line of work after we've nailed `--juans` and one multi-target dispatch.
- **84000 ingest expansion**: separate effort. The current `data_sources.code='84000'` import covers 371 of ~1109 Toh works in the FRBR work table. To unblock Mahāparinirvāṇa / Śūraṅgama / others, we need either a bulk re-ingest from 84000's source tree or a sūtra-by-sūtra fetch using their published reading-page HTML.

## Acceptance criteria for Batch 2 closure

- `prajna_25k_zh_bo` and `laṅkāvatāra_zh_bo` (if Toh 107 has chunks) defined in `MVP_PAIRS`.
- `--juans` flag merged with a smoke test against an existing pair.
- T0223 all-juans run completed across 3–4 sessions; pairs land in DB.
- API endpoints verified for both new text_a ids.
- Reader 「按段对读」 panel verified for both new sūtras.
- README + CHANGELOG entries committed in the same week as the last run.
- `project_fojin_alignment_state.md` memory updated with the new running totals.

## Out of scope (deliberate)

- No FRBR Work spine governance work — that line is still parked per the 2026-06-01 decision in `project_fojin_frbr_works.md`. Mahāyāna 汉藏 alignment growth happens at the chunk-level table, not the Work table.
- No frontend changes. The existing 「跨藏对照」 / 「按段对读」 panel handles new pairs transparently.
- No new dictionary or RAG work. Alignment-pipeline progress is the entire scope of this roadmap.
