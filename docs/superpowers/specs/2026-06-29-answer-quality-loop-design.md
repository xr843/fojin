# Answer-Quality Loop — Design (v1: Bad-Answer Queue)

**Date:** 2026-06-29
**Status:** Draft (pending user review)
**Scope:** fojin chat product — make low-quality AI answers observable and reviewable; produce a labeled dataset that fuels later improvement.

---

## 1. Problem & Motivation

fojin's chat is the product (问答:阅读 ≈ 3.5:1; on 2026-06-29 active users read 0 sutras). But answer
quality is a blind spot:

- 7-day volume: 750 messages / 53 active users, yet **explicit feedback rate is 0.1%** — "好评率 100%"
  is statistically meaningless.
- Behavioral signals exist only as aggregate rates (citation-click 6.7% / copy 1.7% / retry 0.8%) from
  fire-and-forget Umami events that are **not linked to a message_id**, so we can see *that* answers are
  retried but never *which* answer was bad.

Result: we cannot find, inspect, or learn from the answers that actually fail.

### The full loop

```
real traffic → detect suspects (v1) → human review + label (v1) → turn labels into fixes (v2) → measure (v3) → back to traffic
```

**v1 lights up the blind spot and accumulates a labeled dataset. It does not itself improve quality —
it is the fuel layer for v2.** The first weeks after v1 are an accumulation period; payoff is in v2.

---

## 2. Goals / Non-Goals

**v1 Goals**
- Surface, from real production traffic, the assistant answers most likely to be low-quality, ranked by a
  suspicion score, each tagged with *why* it was flagged.
- Let the sole admin review each one against the original question + answer + the cited passages, and record
  a verdict (good/bad), a failure category, and a free note.
- Persist those verdicts (plus a snapshot of why it was flagged) as a labeled dataset.

**v1 Non-Goals (explicit)**
- No change to frontend event instrumentation (Umami events stay as-is).
- No schema change to the hot `chat_messages` table.
- No change to the RAG / chat generation path.
- No eval-gold export, no RAG re-tuning, no retry detection, no feedback-UX change. These are later phases.

**Success criteria**
- The admin can open one screen and, in a single sitting, triage the top-N most-suspect recent answers.
- Every reviewed answer leaves the queue and becomes a labeled row.
- Zero user-facing surface change; zero risk to the chat path (admin-only, read-only detection).

---

## 3. Architecture

Chosen approach: **on-demand SQL detection + one thin review table.** Detection is computed live from
existing data on every queue load; the only new persistent state is the admin's review verdicts.

Rejected alternatives:
- *Materialized suspicion column on `chat_messages` + background scorer* — requires a migration on the hot
  table and write-path coupling; over-engineered for 750 msg/week; scores are derivable from already-stored
  `sources` anyway.
- *Event-linkage first (instrument retry/citation_click with message_id)* — touches frontend + event
  pipeline, and Umami events don't join back relationally; this is exactly the v1.1 fast-follow, deferred.

At 750 messages/week, live SQL over `chat_messages` is milliseconds; no precomputation or background jobs.

---

## 4. Data Model

New table `answer_reviews` (alembic `0164`, revises `0163`). No change to `chat_messages`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `message_id` | int FK→`chat_messages.id`, **unique** | the reviewed assistant message |
| `verdict` | str(10) | `good` / `bad` |
| `failure_category` | str(20) \| null | bad only: `recall` / `hallucination` / `prompt` / `data` / `other` |
| `note` | text \| null | free note |
| `detection_reasons` | JSON | snapshot of reason tags that put it in the queue |
| `suspicion_score` | float | snapshot of the score at review time |
| `reviewed_by` | int FK→`users.id` | the admin |
| `reviewed_at` | datetime | |

Snapshotting `detection_reasons` + `suspicion_score` means the labeled dataset records *why* each item was
flagged — ready-made training signal for v2 (eval-gold export, RAG fixes). `unique(message_id)` makes review
idempotent (re-submit = update).

---

## 5. Detection Logic

Service `build_bad_answer_queue()`: pair each assistant message with its preceding user message in the same
session, apply the detectors, sum weighted hits into `suspicion_score`, sort descending, **exclude any
message already present in `answer_reviews`**.

| Detector | Trigger | Source | Weight |
|---|---|---|---|
| `downvoted` | `feedback = 'down'` | `chat_messages` | highest (unambiguous) |
| `abnormal` | content too short / error placeholder | `content` | high |
| `no_citation` | `sources` empty or unparseable | `sources` | medium |
| `weak_evidence` | `max(source.score) < THRESHOLD_WEAK` | `sources` JSON | scaled by how far below |

**Threshold calibration:** the queue endpoint also returns the percentile distribution of `max(source.score)`
over the window. `THRESHOLD_WEAK` defaults to the 10th percentile and is a config/query parameter, calibrated
against the real distribution after deploy — not guessed.

**Robustness:** old messages may have null/odd `sources` JSON → defensive parsing; on parse failure tag as
`no_citation`/`unparseable`, never raise.

**Refusals:** distinguishing a correct out-of-scope refusal from a wrong one is unreliable to automate, so
v1 does not special-case refusals. A wrong refusal surfaces anyway via `no_citation` (it cites nothing); a
correct refusal also surfaces there and the reviewer marks it `good` — low-cost noise that is itself a
useful label. `未引经率` is ~0% today, so `no_citation` volume is small.

Each item carries its `reason_tags`; the queue is filterable by tag so the admin can triage by failure mode.

---

## 6. API

Reuse the existing `/admin/*` auth dependency (the dashboard already has `/admin/stats/...`). Three endpoints.

**`GET /admin/answer-quality/queue`** — fetch the queue
- query: `window` (days, default 90), `min_suspicion` (default 0), `category` (filter by reason tag),
  `limit` (default 50), `offset`
- returns:
  ```jsonc
  {
    "total_unreviewed": 137,
    "score_distribution": { "p10": 0.42, "p25": 0.51, "p50": 0.63, "p90": 0.78 },
    "items": [{
      "message_id": 9123, "session_id": 880,
      "question": "...", "answer": "...",
      "sources": [{ "text_id": 251, "juan_num": 1, "score": 0.38, "chunk_text": "...", "title_zh": "般若波羅蜜多心經" }],
      "reason_tags": ["weak_evidence", "no_citation"],
      "suspicion_score": 6.5,
      "feedback": null, "created_at": "2026-06-28T13:..."
    }]
  }
  ```

**`POST /admin/answer-quality/reviews`** — submit a review
- body: `{ message_id, verdict: "good"|"bad", failure_category?, note? }`
- upserts `answer_reviews` by `message_id` (ON CONFLICT DO UPDATE), snapshotting the item's current
  `reason_tags` + `suspicion_score`; returns `{ ok, remaining_unreviewed }`. The item leaves the queue.

**`GET /admin/answer-quality/reviews/stats`** — labeled-dataset overview (loop dashboard)
- returns `{ reviewed_total, good, bad, by_category: { recall: 12, hallucination: 3, ... }, last_reviewed_at }`.

All admin-only; detection read-only; review idempotent. No new externally-exposed surface.

---

## 7. Admin UI

New tab **「差答案队列」** under 管理 (`/admin/answer-quality`), same shell as the existing 数据概览; antd,
following `AdminDashboardPage` patterns.

- Header: `未复核 137 条` + `score p10/p50` hint (helps calibrate the threshold) + filters (reason tags
  multi-select, time window, min suspicion).
- Table columns: `时间 | 问题(truncated) | 原因标签(chips) | 可疑度 | 操作`.
- Row expand: full question + full answer + cited-passages table (title_zh / juan / score / chunk_text, the
  weak-evidence passage marked red) + current feedback.
- Inline review: `good / bad` toggle → on `bad`, show `failure_category` select + `note` textarea → 提交
  calls the review endpoint; the row is optimistically removed and the count decrements.
- Empty state: 「队列已清空 🎉」.
- Keyboard flow (`g`/`b`/`Enter`) is a nice-to-have, not in v1.

No frontend event change, no change to the chat path — admin read + one table write, zero user-facing risk.

---

## 8. Error Handling, Testing, Rollout

**Error handling**
- Defensive `sources` JSON parsing (null/old/odd rows → `no_citation`/`unparseable`, never 500).
- Empty queue → 🎉 state. Non-admin → 403 (reuse guard). Review upsert idempotent.
- Detection bounded by `window` + `limit`; never full-scans history.

**Testing** (all CI-safe; no corpus/vectors)
- Unit: detector functions are pure (message + sources → reason_tags + suspicion_score); table-driven tests
  mirroring `test_retrieval_metrics.py`; cover each detector, combinations, and malformed sources.
- API: `test_admin.py`-style — queue ranks suspects, review removes from queue + writes the snapshot,
  non-admin 403; small `chat_messages` fixture.

**Migration / rollout**
- alembic `0164` (revises `0163`) creates `answer_reviews`. Verify prod `alembic_version` + file chain
  before deploy.
- Backend migration auto-applies via `entrypoint alembic upgrade head`. Admin-only → backend can ship
  independently with zero user-facing risk. Admin tab ships on the next frontend rebuild (manually build
  frontend + verify lazy chunk per deploy convention).
- After deploy, call the queue endpoint once to read `score_distribution` and set `THRESHOLD_WEAK`.

**Config (no magic numbers)**: `THRESHOLD_WEAK` (default p10), abnormal-length threshold, error-placeholder
patterns, default window — all in one config block.

---

## 9. Roadmap Beyond v1

**v1.1 — server-side retry detection (committed fast-follow).** Detect dissatisfaction-retries (same/similar
user question re-asked within the same session shortly after an answer → flag the prior assistant message)
and add it as a 5th detector. The strongest *implicit* negative signal; backend-only, preserves v1's
zero-user-risk property; slots into the queue as one more reason tag. **Open item:** today's `chat_retry`
event fires only on *failed*-answer retries — true dissatisfaction-retry needs a same-question-resubmit
heuristic, to be defined against the real queue once v1 is live.

**Parallel track — lower feedback friction.** Make 👍👎 more prominent / add a one-tap "没帮到" so the 0.1%
explicit-feedback rate rises; the `downvoted` detector and the labeled dataset both benefit. This is a
*product-surface* change (taste, A/B-able, self-selection bias) so it is decoupled from the queue and can
ship anytime; it compounds independently. Complementary to v1.1: retry = silent dissatisfaction (behavioral,
unbiased); feedback = stated dissatisfaction (explicit, biased).

**v2 — turn labels into improvement.**
- One-click export of reviewed-`bad` cases into the eval gold set (`test_set.json`), so the regression gate
  watches real failure modes, not synthetic ones.
- Failure-category-driven fixes: `recall`/`weak_evidence` → retrieval tuning (hard-negative mining,
  re-chunk, threshold/reranker) or, when no good passage exists, a **corpus gap** fed to the source-depth /
  FRBR ingest backlog; `hallucination`/`prompt` → prompt/guard tuning.
- Sample real questions through the existing LLM-judge for per-message scores; judge-low-score becomes
  another detector and detects drift on the real distribution.

**v3 — systemic / proactive.**
- Quality-trend dashboard: bad-rate over time, by category — does shipping fixes move the needle?
- Demand-side coverage analysis: cluster real questions; find topic clusters with high bad-rate or zero
  corpus coverage; prioritize data + RAG work by actual demand.

**Strategic payoff:** this loop is the demand-driven scheduler for the other tracks (source depth, RAG
tuning, model/cost choice) — turning "what should I work on" from guesswork into a queue ranked by real
failures.

---

## 10. Operational Notes

- Review load: at ~10–30% suspect of 750 msg/week ≈ 75–225 items/week. Ranking quality matters — the admin
  reviews the high-yield top-N, not everything. This is why the suspicion-score ordering is core to v1.
- Don't over-build detectors before seeing real queue output; v1 ships 4 detectors + snapshots precisely so
  more can be added cheaply once calibrated against reality.
