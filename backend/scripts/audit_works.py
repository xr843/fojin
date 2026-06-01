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
