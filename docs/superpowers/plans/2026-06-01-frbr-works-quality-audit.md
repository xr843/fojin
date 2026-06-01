# FRBR Works Quality Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a read-only, reproducible audit of the FRBR Work spine (works / work_witnesses / work_aliases) that quantifies how much real cross-canon aggregation exists and how trustworthy the heuristic Pass-1 groupings are — so the decision to invest in governance (Phase 1) and Work-level aligned reading (Phase 2) is made on data, not on guesses.

**Architecture:** A new `audit_works.py` script mirroring the existing `build_works.py` shape — a pure, unit-testable core (classification + metric aggregation over plain dataclass rows) wrapped by a thin async DB-fetch shell. Read-only (SELECT only), safe to run against production. Emits a JSON blob + a human summary, and dumps an audit sample (largest + random Pass-1 clusters with their witness titles) for manual error-rate spot-check. Phase 1/2 are scoped here as architecture + decision gates and become their own plans once the audit lands.

**Tech Stack:** Python 3.11, SQLAlchemy 2.0 async, `app.database.async_session`, pytest (pure-logic tests, no DB fixture needed), argparse. No new dependencies.

---

## Why this plan stops at Phase 0 (scope rationale)

The agreed direction is **measure → govern → payoff**. Per the writing-plans Scope Check, each plan must produce working, testable software on its own and must not contain fake-precise placeholders.

Phase 1 (governance tooling) and Phase 2 (Work-level aligned reading) have code whose exact shape depends on the audit's findings — e.g. the merge/split CLI's priority and the alignment data model only make sense once we know the singleton ratio, the cross-canon coverage, and the Pass-1 false-merge rate. Writing TDD steps for them now would be inventing semantics against unknown data, which is the placeholder trap in disguise.

So this plan fully specifies **Phase 0** (runnable now) and specifies Phase 1/2 as **architecture + concrete decision gates**. After Phase 0 produces numbers, each later phase gets its own detailed plan calibrated to those numbers.

## Verified background facts (do not re-investigate)

From `backend/scripts/build_works.py` and `backend/app/models/work.py`:

- Every `buddhist_texts` row ends up in **exactly one** Work, assigned by four ordered passes:
  - **Pass 1 — cross-pillar Skt-title clustering** (the high-value, **highest-risk** bit): groups every text with a non-empty `title_sa` by a normalized Skt-title key. False merges (different texts sharing a normalized title) live here. Creates `work_aliases(scheme='skt_title')`.
  - **Pass 2 — SuttaCentral**: `SC-<uid>` texts → Work anchored by `sc_root_uid`, witness `confidence='verified'`. Creates `work_aliases(scheme='sc_uid')`.
  - **Pass 3 — 84000**: `84K-toh<N>` texts → Work anchored by `toh_number`, witness `confidence='verified'`. Creates `work_aliases(scheme='toh')`.
  - **Pass 4 — singletons**: every remaining text → a one-witness Work keyed by `cbeta_id`, witness `confidence='auto'`.
- **The originating pass is NOT stored on any row.** It is reconstructed from the Work's alias schemes with priority `skt_title > sc_uid > toh > singleton` (a Work is created in exactly one pass, so the highest-priority alias present identifies it).
- `WorkWitness` columns: `role` (root|translation|commentary|edition|fragment), `lang`, `canon` (taisho|xuzang|pali|kangyur|gretil|...), `confidence` (verified|auto|tentative).
- Tables: `works`, `work_witnesses`, `work_aliases`, `buddhist_texts`.

## File Structure

- **Create:** `backend/scripts/audit_works.py` — pure core (`classify_origin`, `cluster_bucket`, `compute_metrics`, `select_audit_targets`, `WorkRow`) + async DB shell (`fetch_rows`, `main`).
- **Create:** `backend/tests/test_audit_works.py` — pytest unit tests over the pure core with synthetic `WorkRow` lists.
- **Create (output, written in Task 4):** `docs/works-audit/2026-06-01-findings.md` — the audit report + the gate decision.

The pure/shell split matches `build_works.py` exactly: classification and aggregation are DB-free and tested in isolation; the shell only fetches and prints.

---

### Task 1: Origin classification + cluster bucketing (pure)

**Files:**
- Create: `backend/scripts/audit_works.py`
- Test: `backend/tests/test_audit_works.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_audit_works.py
from scripts.audit_works import classify_origin, cluster_bucket


def test_classify_origin_priority():
    # skt_title wins even when other schemes co-occur
    assert classify_origin({"skt_title", "sc_uid"}) == "pass1_skt"
    assert classify_origin({"sc_uid"}) == "pass2_sc"
    assert classify_origin({"toh"}) == "pass3_toh"
    assert classify_origin({"sc_uid", "toh"}) == "pass2_sc"
    assert classify_origin(set()) == "pass4_singleton"
    assert classify_origin({"taisho"}) == "pass4_singleton"  # unknown scheme → singleton


def test_cluster_bucket_boundaries():
    assert cluster_bucket(1) == "1"
    assert cluster_bucket(2) == "2"
    assert cluster_bucket(5) == "3-5"
    assert cluster_bucket(6) == "6-10"
    assert cluster_bucket(15) == "11-15"
    assert cluster_bucket(16) == ">15"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_audit_works.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.audit_works'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/scripts/audit_works.py
"""Read-only audit of the FRBR Work spine.

Quantifies real cross-canon aggregation and the trustworthiness of heuristic
Pass-1 (Skt-title) groupings. SELECT-only — safe against production.

Pure core (classify/aggregate over dataclass rows) is unit-tested in isolation,
mirroring build_works.py. The async shell only fetches rows and prints.

Usage:
  python scripts/audit_works.py                 # human summary + JSON to stdout
  python scripts/audit_works.py --json           # JSON only
  python scripts/audit_works.py --sample-out audit_sample.md   # dump sample for manual review
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Priority order: a Work is created in exactly one pass; the highest-priority
# alias scheme present identifies that pass.
_ORIGIN_PRIORITY = (("skt_title", "pass1_skt"), ("sc_uid", "pass2_sc"), ("toh", "pass3_toh"))


def classify_origin(alias_schemes: set[str]) -> str:
    for scheme, origin in _ORIGIN_PRIORITY:
        if scheme in alias_schemes:
            return origin
    return "pass4_singleton"


def cluster_bucket(n: int) -> str:
    if n <= 1:
        return "1"
    if n == 2:
        return "2"
    if n <= 5:
        return "3-5"
    if n <= 10:
        return "6-10"
    if n <= 15:
        return "11-15"
    return ">15"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_audit_works.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/audit_works.py backend/tests/test_audit_works.py
git commit -m "feat(works-audit): origin classification + cluster bucketing (pure)"
```

---

### Task 2: Metric aggregation + audit-target selection (pure)

**Files:**
- Modify: `backend/scripts/audit_works.py`
- Test: `backend/tests/test_audit_works.py`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_audit_works.py
from scripts.audit_works import WorkRow, compute_metrics, select_audit_targets


def _row(work_id, origin, canons, confidences):
    return WorkRow(
        work_id=work_id,
        slug=f"w{work_id}",
        title=f"title-{work_id}",
        origin_pass=origin,
        witness_count=len(confidences),
        canons=tuple(canons),
        confidences=tuple(confidences),
    )


def test_compute_metrics_core_ratios():
    rows = [
        _row(1, "pass1_skt", ["taisho", "kangyur"], ["auto", "auto"]),   # multi + cross-canon
        _row(2, "pass1_skt", ["taisho"], ["auto"]),                       # singleton
        _row(3, "pass2_sc", ["pali"], ["verified"]),                      # singleton, verified
        _row(4, "pass4_singleton", ["taisho"], ["auto"]),                 # singleton
    ]
    m = compute_metrics(rows)
    assert m["total_works"] == 4
    assert m["total_witnesses"] == 5
    assert m["multi_witness_works"] == 1
    assert m["singleton_works"] == 3
    assert m["cross_canon_works"] == 1
    assert m["by_origin"]["pass1_skt"]["works"] == 2
    assert m["by_origin"]["pass1_skt"]["witnesses"] == 3
    assert m["confidence_distribution"]["verified"] == 1
    assert m["confidence_distribution"]["auto"] == 4
    assert m["pass1_cluster_histogram"]["2"] == 1
    assert m["pass1_cluster_histogram"]["1"] == 1


def test_select_audit_targets_is_deterministic_and_pass1_multi_only():
    rows = [_row(i, "pass1_skt", ["taisho", "kangyur"], ["auto"] * (i % 4 + 2)) for i in range(50)]
    rows += [_row(99, "pass2_sc", ["pali"], ["verified", "verified"])]  # must be excluded
    top, sample = select_audit_targets(rows, top_n=5, random_n=5, seed=20260601)
    assert all(r.origin_pass == "pass1_skt" for r in top + sample)
    assert [r.witness_count for r in top] == sorted([r.witness_count for r in top], reverse=True)
    # deterministic: same seed → same ids
    top2, sample2 = select_audit_targets(rows, top_n=5, random_n=5, seed=20260601)
    assert [r.work_id for r in sample] == [r.work_id for r in sample2]
    # top and sample do not overlap
    assert not ({r.work_id for r in top} & {r.work_id for r in sample})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_audit_works.py -v`
Expected: FAIL — `ImportError: cannot import name 'WorkRow'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to backend/scripts/audit_works.py (after cluster_bucket)

@dataclass(frozen=True)
class WorkRow:
    work_id: int
    slug: str
    title: str
    origin_pass: str
    witness_count: int
    canons: tuple[str, ...]
    confidences: tuple[str, ...]


def compute_metrics(rows: list[WorkRow]) -> dict:
    total_works = len(rows)
    total_witnesses = sum(r.witness_count for r in rows)
    multi = sum(1 for r in rows if r.witness_count >= 2)
    singleton = total_works - multi
    cross_canon = sum(1 for r in rows if len(set(r.canons)) >= 2)

    by_origin: dict[str, dict[str, int]] = {}
    conf_dist: dict[str, int] = {}
    pass1_hist: dict[str, int] = {}
    for r in rows:
        b = by_origin.setdefault(r.origin_pass, {"works": 0, "witnesses": 0, "multi": 0})
        b["works"] += 1
        b["witnesses"] += r.witness_count
        if r.witness_count >= 2:
            b["multi"] += 1
        for c in r.confidences:
            conf_dist[c] = conf_dist.get(c, 0) + 1
        if r.origin_pass == "pass1_skt":
            bkt = cluster_bucket(r.witness_count)
            pass1_hist[bkt] = pass1_hist.get(bkt, 0) + 1

    ratio = lambda n: round(n / total_works, 4) if total_works else 0.0
    return {
        "total_works": total_works,
        "total_witnesses": total_witnesses,
        "multi_witness_works": multi,
        "singleton_works": singleton,
        "multi_witness_ratio": ratio(multi),
        "cross_canon_works": cross_canon,
        "cross_canon_ratio": ratio(cross_canon),
        "by_origin": by_origin,
        "confidence_distribution": conf_dist,
        "pass1_cluster_histogram": pass1_hist,
    }


def select_audit_targets(
    rows: list[WorkRow], *, top_n: int = 20, random_n: int = 20, seed: int = 20260601
) -> tuple[list[WorkRow], list[WorkRow]]:
    """Pass-1 multi-witness Works are the false-merge risk surface. Return the
    largest `top_n` clusters plus a deterministic random `random_n` sample of the
    rest, for manual error-rate spot-check."""
    pass1_multi = [r for r in rows if r.origin_pass == "pass1_skt" and r.witness_count >= 2]
    by_size = sorted(pass1_multi, key=lambda r: (-r.witness_count, r.slug))
    top = by_size[:top_n]
    top_ids = {r.work_id for r in top}
    remaining = [r for r in by_size if r.work_id not in top_ids]
    rng = random.Random(seed)
    sample = rng.sample(remaining, min(random_n, len(remaining)))
    return top, sample
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_audit_works.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/audit_works.py backend/tests/test_audit_works.py
git commit -m "feat(works-audit): metric aggregation + audit-target selection (pure)"
```

---

### Task 3: Async DB-fetch shell + CLI

**Files:**
- Modify: `backend/scripts/audit_works.py`

This task has no unit test (it is a thin I/O shell, exactly like `build_works.main`); it is verified by the real run in Task 4. It must issue **only SELECT** statements.

- [ ] **Step 1: Add the fetch shell + main**

```python
# add to backend/scripts/audit_works.py (after select_audit_targets)
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.work import Work


async def fetch_rows() -> list[WorkRow]:
    """SELECT-only. Loads every Work with its witnesses and aliases eagerly,
    then projects to the pure WorkRow shape."""
    async with async_session() as session:
        result = await session.execute(
            select(Work).options(
                selectinload(Work.witnesses),
                selectinload(Work.aliases),
            )
        )
        works = result.scalars().unique().all()
    rows: list[WorkRow] = []
    for w in works:
        schemes = {a.scheme for a in w.aliases}
        rows.append(
            WorkRow(
                work_id=w.id,
                slug=w.slug,
                title=w.title_primary,
                origin_pass=classify_origin(schemes),
                witness_count=len(w.witnesses),
                canons=tuple(wit.canon or "?" for wit in w.witnesses),
                confidences=tuple(wit.confidence for wit in w.witnesses),
            )
        )
    return rows


def render_summary(m: dict) -> str:
    lines = [
        "FRBR Works audit",
        f"  works={m['total_works']}  witnesses={m['total_witnesses']}",
        f"  multi-witness={m['multi_witness_works']} ({m['multi_witness_ratio']:.1%})  "
        f"singleton={m['singleton_works']}",
        f"  cross-canon works={m['cross_canon_works']} ({m['cross_canon_ratio']:.1%})",
        "  by origin pass:",
    ]
    for origin, b in sorted(m["by_origin"].items()):
        lines.append(f"    {origin:16} works={b['works']:>6}  witnesses={b['witnesses']:>6}  multi={b['multi']:>5}")
    lines.append(f"  confidence: {m['confidence_distribution']}")
    lines.append(f"  pass1 cluster sizes: {m['pass1_cluster_histogram']}")
    return "\n".join(lines)


def render_sample(top: list[WorkRow], sample: list[WorkRow]) -> str:
    out = ["# Pass-1 audit sample (manual error-rate spot-check)\n"]
    for label, group in (("Largest clusters", top), ("Random sample", sample)):
        out.append(f"## {label}\n")
        for r in group:
            out.append(f"- **{r.title}** (`{r.slug}`, id={r.work_id}) — {r.witness_count} witnesses, canons={sorted(set(r.canons))}")
            out.append(f"  - [ ] correct grouping?  notes: ")
        out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only FRBR Works audit.")
    parser.add_argument("--json", action="store_true", help="emit metrics JSON only")
    parser.add_argument("--sample-out", metavar="PATH", help="write the Pass-1 audit sample to PATH")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--random-n", type=int, default=20)
    args = parser.parse_args()

    rows = asyncio.run(fetch_rows())
    metrics = compute_metrics(rows)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(render_summary(metrics))
        print("\n" + json.dumps(metrics, ensure_ascii=False))

    if args.sample_out:
        top, sample = select_audit_targets(rows, top_n=args.top_n, random_n=args.random_n)
        Path(args.sample_out).write_text(render_sample(top, sample), encoding="utf-8")
        print(f"\nwrote audit sample → {args.sample_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the full test file still passes and the module imports**

Run: `cd backend && python -m pytest tests/test_audit_works.py -v && python -c "import scripts.audit_works"`
Expected: PASS (6 passed) and no import error.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/audit_works.py
git commit -m "feat(works-audit): async DB-fetch shell + CLI (read-only)"
```

---

### Task 4: Run against the database and write the findings report

**Files:**
- Create: `docs/works-audit/2026-06-01-findings.md`

Run the audit against a real database. Prefer a production **read replica / snapshot**; if running against prod directly, it is SELECT-only and low-cost (one indexed scan of `works` + eager loads). Confirm `DATABASE_URL` (or the container env) points where you intend before running.

- [ ] **Step 1: Run the audit + dump the sample**

Run (in the backend environment with DB access):
```bash
cd backend
python scripts/audit_works.py --sample-out /tmp/works_audit_sample.md
```
Expected: a summary like `works=10295 witnesses=… multi-witness=… cross-canon works=…` plus the by-origin / confidence / cluster-histogram lines, and a written sample file.

- [ ] **Step 2: Manually review the sample**

Open `/tmp/works_audit_sample.md`. For each of the ~40 Pass-1 clusters, judge whether the grouped witnesses are genuinely the same work (check the titles/canons). Tick the checkboxes and count wrong groupings → that is the **Pass-1 false-merge rate**.

- [ ] **Step 3: Write the findings report**

Create `docs/works-audit/2026-06-01-findings.md` containing: the metrics JSON, the by-origin table, the cluster histogram, the measured Pass-1 false-merge rate (e.g. "3 / 40 = 7.5%"), and a one-paragraph read of what it means (is the spine aggregating, or mostly singletons?).

- [ ] **Step 4: Commit**

```bash
git add docs/works-audit/2026-06-01-findings.md
git commit -m "docs(works-audit): Phase 0 findings + Pass-1 false-merge rate"
```

---

## Decision Gate — Phase 0 → Phase 1 / Phase 2

Read the findings and route. These thresholds are starting points; adjust with judgment.

| Signal from Phase 0 | Interpretation | Next move |
|---|---|---|
| `multi_witness_ratio` very low (e.g. <15%) **and** `cross_canon_works` small | Spine is mostly singletons — it is a catalog, not an aggregation. The "跨藏" payoff barely exists yet. | **Before any governance or alignment**, revisit `build_works` recall (why so few witnesses cluster?) or ingest depth. Do NOT build Phase 1/2 on a hollow spine. |
| Pass-1 false-merge rate **high** (e.g. >10%) | Heuristic clustering is wrong often enough to erode trust the moment it is surfaced. | **Phase 1 (governance) is top priority.** Aligned reading on wrong groupings is worse than nothing. |
| Pass-1 false-merge rate **low** (e.g. <5%) **and** meaningful `cross_canon_works` | Spine is trustworthy and genuinely aggregating. | **Skip heavy governance; go to Phase 2** (Work-level aligned reading), add a lightweight flag-bad-grouping path only. |
| Mixed (decent coverage, ~5–10% error) | Trust is salvageable with targeted cleanup. | **Phase 1-lite**: confidence promotion + targeted fixes for the largest clusters only, then Phase 2. |

---

## Phase 1 — Governance (architecture + gate; expand to its own plan after the audit)

**Trigger:** Pass-1 false-merge rate ≥ ~5% (from Task 4).

**Architecture:**
- **Migration** (`alembic`): add `reviewed_at TIMESTAMPTZ NULL`, `reviewed_by VARCHAR NULL` to `work_witnesses`; add a `work_review_log` table (action, work_id, payload JSON, actor, ts) for an audit trail. Additive only — consistent with the "purely additive" build_works contract.
- **CLI first, UI later** (`backend/scripts/work_admin.py`): operations `promote`/`demote` (auto↔verified↔tentative), `merge` (fold Work B's witnesses into A, repoint aliases, delete B), `split` (move named witnesses out to a new Work), `flag` (mark a cluster tentative). Every op writes `work_review_log` and is idempotent. Pure decision logic (which witnesses move, alias reconciliation) is unit-tested in isolation, exactly like `build_works`.
- **Re-run safety:** `build_works` must not silently revert manual reviews — add a guard so it skips witnesses with `confidence='verified'` or a non-null `reviewed_at`. (This is a concrete `build_works` change Phase 1 must include.)
- **Optional admin API** only if a human reviewer other than the CLI operator is needed — defer until the CLI proves the workflow.

**Why this shape:** governance is a data-authority problem; a scripted, audited, idempotent CLI is the cheapest correct starting point and avoids building UI before the operations are validated.

## Phase 2 — Work-level aligned reading + chat synergy (architecture + gate)

**Trigger:** Phase 0 (and Phase 1 if triggered) show a trustworthy, genuinely-aggregating spine.

**Architecture:**
- **Reading payoff:** promote the existing text-level `alignment_pairs` to a Work view — given a Work, assemble its witnesses' aligned segments into a parallel-reading layout (the differentiator nobody else has). New read-only endpoint `GET /api/works/{slug}/alignment`; reuse `alignment_pairs`, do not duplicate it. Exact data model decided after inspecting `alignment_pairs` cardinality in the audit follow-up.
- **Chat synergy (shared investment):** extend RAG retrieval from text-level to **Work-level** — one query can recall all witnesses of a sutra, addressing the known 本经召回 gap. Reuses the same Work→witnesses map Phase 1 governs, so one data investment pays off in both reading and `/chat`.

**Why gated:** aligned reading and Work-level recall both amplify whatever groupings exist — correct or not. They must come after trust is established, or they amplify errors into more surfaces.

---

## Self-Review

**1. Spec coverage:**
- "measure" → Tasks 1–4 (audit script + run + findings). ✓
- "govern" → Phase 1 architecture + gate. ✓ (detailed plan deferred by design, see scope rationale)
- "payoff (aligned reading)" → Phase 2 architecture + gate. ✓
- "chat 本经召回 synergy" → Phase 2 chat synergy. ✓
- Decision gate connecting measure → govern/payoff. ✓

**2. Placeholder scan:** Phase 0 tasks contain complete code, exact commands, and expected output — no TBD/TODO in executable steps. Phase 1/2 are explicitly scoped as architecture (not pretend-precise code) with documented rationale; this is intentional, not a placeholder gap.

**3. Type consistency:** `WorkRow` fields (`work_id`, `slug`, `title`, `origin_pass`, `witness_count`, `canons`, `confidences`) are defined in Task 2 and used identically in the Task 1 test helper, Task 2 tests, and Task 3 `fetch_rows`. `classify_origin` returns the four `passN_*` strings consumed by `compute_metrics`/`select_audit_targets`. `compute_metrics` keys referenced in `render_summary` (`total_works`, `multi_witness_ratio`, `by_origin`, `confidence_distribution`, `pass1_cluster_histogram`) all exist in its return dict. Consistent. ✓
