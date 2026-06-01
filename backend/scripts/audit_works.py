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
    # Exclude the unknown-canon sentinel ("?") and empties so a real-canon +
    # null-canon witness pair is NOT miscounted as cross-canon (feeds the gate).
    cross_canon = sum(1 for r in rows if len({c for c in r.canons if c and c != "?"}) >= 2)

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

    def ratio(n: int) -> float:
        return round(n / total_works, 4) if total_works else 0.0
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
        # defensive; selectinload (unlike joinedload) does not duplicate parent rows
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
            out.append("  - [ ] correct grouping?  notes: ")
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
