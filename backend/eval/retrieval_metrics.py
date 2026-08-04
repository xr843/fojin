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

# Relevance grading of a gold entry:
#   2 = 正解 — the canonical source the answer is expected to cite
#   1 = 等价可接受来源 — an equally defensible alternative (e.g. 大乘廣五蘊論
#       answers 五蕴 as well as the 心經 does). Counted by the lenient family
#       only, so "the retriever found a good source, just not THE one" stops
#       reading as a miss.
STRICT_RELEVANCE = 2
LENIENT_RELEVANCE = 1

# The two questions a retriever answers by different mechanisms:
#   attribution — "「色不异空」出自哪部经" : the source identity IS the answer.
#                 A lookup problem; similarity search structurally under-serves it.
#   passage     — "什么是中道"           : any doctrinally sound passage works.
#                 A similarity problem, which is what dense retrieval is for.
# Aggregating them together hides which mechanism is failing, so they are
# bucketed apart. A gold-bearing question with no annotation is UNSPECIFIED —
# deliberately not folded into "passage", so the gap stays visible in the report.
# A third case that is neither: in-scope questions with no canonical source at
# all ("初学佛应该先读哪些经典"). Forcing gold onto them would make the ruler lie;
# leaving them bare would be indistinguishable from a question someone forgot to
# annotate — so ADVISORY is declared explicitly and scored on answer quality only.
ATTRIBUTION = "attribution"
PASSAGE = "passage"
ADVISORY = "advisory"
UNSPECIFIED = "unspecified"
_VALID_TYPES = (ATTRIBUTION, PASSAGE)

# detect_regressions only cares about quality metrics, not bookkeeping counts.
# "lenient_" covers the graded family; the lenient gold COUNT is deliberately
# named `num_gold_lenient` so it does not match and get gated as if it were a
# quality metric.
_METRIC_PREFIXES = ("recall@", "hit@", "precision@", "mrr", "lenient_")


def normalize_title(title: str) -> str:
    """Fold a canon title to a comparison key (NFKC + 繁→简 + strip non-word)."""
    if not title:
        return ""
    s = unicodedata.normalize("NFKC", title)
    s = _t2s.convert(s)
    s = _STRIP_RE.sub("", s)
    return s.casefold()


def gold_entries(question: dict, min_relevance: int = 0) -> list[dict]:
    """Normalize a question's gold set to ``[{title, juan, relevance}]``.

    ``min_relevance`` filters the result to entries graded at least that high;
    the default of 0 keeps every entry, so existing callers are unaffected.
    Title-level ``reference_sources`` carry ``DEFAULT_RELEVANCE`` (2), so a
    corpus annotated only that way scores identically under strict and lenient.
    """
    structured = question.get("gold_sources")
    if structured:
        out = []
        for g in structured:
            title = normalize_title(g.get("title", ""))
            if not title:
                continue
            relevance = g.get("relevance", DEFAULT_RELEVANCE)
            if relevance < min_relevance:
                continue
            out.append({"title": title, "juan": g.get("juan"), "relevance": relevance})
        return out

    return [
        {"title": normalize_title(t), "juan": None, "relevance": DEFAULT_RELEVANCE}
        for t in question.get("reference_sources", [])
        if normalize_title(t) and min_relevance <= DEFAULT_RELEVANCE
    ]


def retrieval_type(question: dict) -> str | None:
    """Which retrieval mechanism this question exercises, or None if it has no gold.

    Out-of-scope questions (no gold at all) belong in neither bucket — they are
    scored on refusal behaviour, not retrieval.
    """
    declared = question.get("retrieval_type")
    if declared == ADVISORY:
        return ADVISORY
    if not gold_entries(question):
        return None
    return declared if declared in _VALID_TYPES else UNSPECIFIED


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


def compute_metrics_graded(
    retrieved: list[tuple], question: dict, ks: tuple[int, ...] = DEFAULT_KS
) -> dict:
    """Strict + lenient retrieval metrics for one question, in one row.

    Strict metrics keep the ORIGINAL key names (``recall@5``, ``hit@5``, …) and
    the original meaning — only ``relevance >= 2`` gold counts — so every stored
    baseline keeps comparing like for like. The lenient family, which also
    credits ``relevance == 1`` equivalents, is added under a ``lenient_`` prefix.

    Also stamps ``retrieval_type`` so :func:`aggregate_by_type` can report
    归属题 and 段落题 apart.
    """
    strict = gold_entries(question, min_relevance=STRICT_RELEVANCE)
    lenient = gold_entries(question, min_relevance=LENIENT_RELEVANCE)

    out = compute_metrics(retrieved, strict, ks)
    lenient_metrics = compute_metrics(retrieved, lenient, ks)
    for key, value in lenient_metrics.items():
        if key == "num_gold":
            # Named so it does NOT match _METRIC_PREFIXES — a change in how many
            # gold entries exist is bookkeeping, not a quality regression.
            out["num_gold_lenient"] = value
        elif key != "num_retrieved":
            out[f"lenient_{key}"] = value
    out["retrieval_type"] = retrieval_type(question)
    return out


def aggregate_by_type(rows: list[dict]) -> dict[str, dict]:
    """Group metric rows by ``retrieval_type`` and aggregate each bucket.

    Rows without a type (out-of-scope questions) are dropped rather than pooled
    into a bucket they don't belong to. Each bucket carries ``n``, its question
    count, so a 3-question bucket isn't read as a stable rate.
    """
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        rtype = row.get("retrieval_type")
        if not rtype:
            continue
        buckets.setdefault(rtype, []).append(row)
    return {rtype: {**aggregate(rs), "n": len(rs)} for rtype, rs in buckets.items()}


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
        vals = [row[key] for row in rows if isinstance(row.get(key), int | float)]
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
        if not isinstance(cur_val, int | float) or not isinstance(base_val, int | float):
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
