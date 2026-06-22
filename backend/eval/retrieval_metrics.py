"""Deterministic retrieval metrics for the AI-chat eval harness.

The existing eval scores answer quality with an LLM judge (slow, costly,
non-reproducible). These functions add a *deterministic* layer: given the
sources RAG actually retrieved and a per-question gold set, compute
Recall@K / Hit@K / MRR / Precision@K by matching canon titles (繁简-folded)
and, when specified, juan numbers.

Gold can be supplied two ways per question in test_set.json:
  - ``reference_sources``: list of canon titles (title-level matching, juan=any)
  - ``gold_sources``:      list of {"title", "juan"(optional), "relevance"(optional)}
``gold_sources`` takes precedence and enables juan-level precision.

Pure logic only — no DB, no network — so the metric layer is unit-tested in CI
while the full eval (which needs the corpus DB) runs on prod/cron.
"""

from __future__ import annotations

import re
import unicodedata

from opencc import OpenCC

_t2s = OpenCC("t2s")

# Strip everything that is not a CJK ideograph or alphanumeric so that
# 《心經》, "心经·", "心经 " all collapse to the same key.
_STRIP_RE = re.compile(r"[^0-9A-Za-z㐀-䶿一-鿿]+")

DEFAULT_RELEVANCE = 2
DEFAULT_KS = (1, 3, 5)
DEFAULT_TOLERANCE = 0.02

# detect_regressions only cares about quality metrics, not bookkeeping counts.
_METRIC_PREFIXES = ("recall@", "hit@", "precision@", "mrr")


def normalize_title(title: str) -> str:
    """Fold a canon title to a comparison key (NFKC + 繁→简 + strip non-word)."""
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", title)
    s = _t2s.convert(s)
    s = _STRIP_RE.sub("", s)
    return s.casefold()


def gold_entries(question: dict) -> list[dict]:
    """Normalize a question's gold set to ``[{title, juan, relevance}]``."""
    structured = question.get("gold_sources")
    if structured:
        out = []
        for g in structured:
            title = normalize_title(g.get("title", ""))
            if not title:
                continue
            out.append({
                "title": title,
                "juan": g.get("juan"),
                "relevance": g.get("relevance", DEFAULT_RELEVANCE),
            })
        return out

    return [
        {"title": normalize_title(t), "juan": None, "relevance": DEFAULT_RELEVANCE}
        for t in question.get("reference_sources", [])
        if normalize_title(t)
    ]


def source_matches_gold(src_title: str, src_juan: int | None, gold: dict) -> bool:
    """True iff a retrieved source matches a gold entry (title + optional juan)."""
    if normalize_title(src_title) != gold["title"]:
        return False
    if gold["juan"] is None:
        return True
    return src_juan == gold["juan"]


def _matched_gold_indices(retrieved: list[tuple], gold: list[dict], k: int) -> set[int]:
    """Indices of gold entries hit by any of the top-k retrieved pairs."""
    hit: set[int] = set()
    for title, juan in retrieved[:k]:
        for gi, g in enumerate(gold):
            if gi not in hit and source_matches_gold(title, juan, g):
                hit.add(gi)
    return hit


def recall_at_k(retrieved: list[tuple], gold: list[dict], k: int) -> float:
    """Fraction of gold entries matched by the top-k retrieved sources."""
    if not gold:
        return 0.0
    return len(_matched_gold_indices(retrieved, gold, k)) / len(gold)


def hit_at_k(retrieved: list[tuple], gold: list[dict], k: int) -> float:
    """1.0 if any gold entry is matched within the top-k, else 0.0."""
    if not gold:
        return 0.0
    return 1.0 if _matched_gold_indices(retrieved, gold, k) else 0.0


def mrr(retrieved: list[tuple], gold: list[dict]) -> float:
    """Reciprocal rank (1-indexed) of the first retrieved source hitting gold."""
    if not gold:
        return 0.0
    for rank, (title, juan) in enumerate(retrieved, start=1):
        if any(source_matches_gold(title, juan, g) for g in gold):
            return 1.0 / rank
    return 0.0


def precision_at_k(retrieved: list[tuple], gold: list[dict], k: int) -> float:
    """Fraction of top-k retrieved sources that match some gold entry."""
    top = retrieved[:k]
    if not top or not gold:
        return 0.0
    relevant = sum(
        1 for title, juan in top if any(source_matches_gold(title, juan, g) for g in gold)
    )
    return relevant / len(top)


def compute_metrics(
    retrieved: list[tuple], gold: list[dict], ks: tuple[int, ...] = DEFAULT_KS
) -> dict:
    """All retrieval metrics for one question.

    Quality metrics are ``None`` when the question has no gold (e.g. out-of-scope)
    so :func:`aggregate` can exclude them rather than dragging the mean to zero.
    """
    has_gold = bool(gold)
    out: dict = {"num_gold": len(gold), "num_retrieved": len(retrieved)}
    for k in ks:
        out[f"recall@{k}"] = recall_at_k(retrieved, gold, k) if has_gold else None
        out[f"hit@{k}"] = hit_at_k(retrieved, gold, k) if has_gold else None
        out[f"precision@{k}"] = precision_at_k(retrieved, gold, k) if has_gold else None
    out["mrr"] = mrr(retrieved, gold) if has_gold else None
    return out


def aggregate(rows: list[dict]) -> dict:
    """Mean of each numeric metric across questions, skipping ``None`` values."""
    if not rows:
        return {}
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    agg: dict = {}
    for key in keys:
        vals = [row[key] for row in rows if isinstance(row.get(key), (int, float))]
        if vals:
            agg[key] = sum(vals) / len(vals)
    return agg


def detect_regressions(
    current: dict, baseline: dict, tolerance: float = DEFAULT_TOLERANCE
) -> list[str]:
    """Quality metrics that dropped from baseline by more than ``tolerance``."""
    regressions = []
    for key, base_val in baseline.items():
        if not key.startswith(_METRIC_PREFIXES):
            continue
        cur_val = current.get(key)
        if not isinstance(cur_val, (int, float)) or not isinstance(base_val, (int, float)):
            continue
        if base_val - cur_val > tolerance:
            regressions.append(
                f"{key}: {cur_val:.3f} < baseline {base_val:.3f} (Δ {cur_val - base_val:+.3f})"
            )
    return regressions


def sources_to_pairs(sources) -> list[tuple]:
    """Adapt retrieved sources (ChatSource objects or dicts) to (title, juan) pairs."""
    pairs = []
    for s in sources:
        if isinstance(s, dict):
            pairs.append((s.get("title_zh", ""), s.get("juan_num")))
        else:
            pairs.append((getattr(s, "title_zh", ""), getattr(s, "juan_num", None)))
    return pairs
