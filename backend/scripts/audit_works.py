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
