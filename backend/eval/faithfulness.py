"""Deterministic citation-faithfulness metrics for the AI-chat eval harness.

The eval already scores answers two ways: an LLM judge (subjective, costly,
non-reproducible) and deterministic *retrieval* metrics (Recall@K/MRR — did we
fetch the right sources?). Neither measures the property fojin stakes its
credibility on: does every citation and quote in the *answer* resolve to a
retrieved source — "每一句都能点回原典"?

That signal already exists at runtime. Production runs each answer through
``enforce_citation_whitelist`` (strips a hallucinated ``【《title》第N卷】``) and
``verify_quoted_content`` (flags a quote that isn't a substring of a retrieved
chunk), then ``build_trust_status`` collapses the result into the same
``ChatTrustState`` the user sees on the message. This module lifts that exact
pipeline into the offline eval so the brand claim becomes a measured,
regression-gate-able number instead of an LLM judge's opinion.

Pure logic — it replays the production guards over an in-memory
``(answer, sources)`` pair, no DB and no network — so it is unit-tested in CI
alongside the other deterministic metric layers, while the full eval (which
needs the corpus DB to *produce* answers) runs on prod/cron with the LLM on.

Measured on the RAW model answer (pre-guard): a rise in mutations is an early
signal that the underlying model's grounding regressed — the runtime guards then
remediate at serve time what this metric counts here.
"""

from __future__ import annotations

from app.schemas.chat import ChatSource
from app.services.chat_trust import build_trust_status
from app.services.citation_guard import enforce_citation_whitelist
from app.services.quote_verifier import verify_quoted_content

# The five states build_trust_status can emit, in descending trust order. Kept
# explicit (rather than imported from the Literal) so the report renders a
# stable, ordered distribution even for states absent from a given run.
TRUST_STATES = (
    "verified",
    "sources_available",
    "citation_corrected",
    "quote_unverified",
    "no_sources",
)

# Grounding rates a regression gate watches. Mirrors retrieval_metrics'
# _METRIC_PREFIXES convention (bookkeeping counts are excluded).
_GATED_RATES = ("citation_grounding_rate", "verified_rate_of_cited")


def compute_faithfulness(answer: str, sources: list[ChatSource]) -> dict:
    """Deterministic citation/quote grounding signal for one answer.

    Replays the production trust pipeline (citation guard → quote verifier →
    trust status) over the raw answer and its retrieved sources. Returns numeric
    fields plus the ``trust_state`` string; the caller aggregates a run's worth
    of these with :func:`aggregate_faithfulness`.
    """
    corrected, citation_mutations = enforce_citation_whitelist(answer, sources)
    # The verifier runs *after* the guard by design (see quote_verifier's
    # module docstring) so quotes attached to already-stripped citations
    # aren't double-flagged.
    _, quote_mutations = verify_quoted_content(corrected, sources)
    trust = build_trust_status(
        answer,
        sources,
        citation_mutations=citation_mutations,
        quote_mutations=quote_mutations,
    )
    citations_grounded = max(0, trust.citation_count - trust.citation_mutation_count)
    return {
        "trust_state": trust.state,
        "citation_count": trust.citation_count,
        "citation_mutations": trust.citation_mutation_count,
        "quote_mutations": trust.quote_mutation_count,
        "citations_grounded": citations_grounded,
        "has_citations": 1 if trust.citation_count else 0,
        # "verified" is the only state with ≥1 citation and zero citation/quote
        # mutations — the literal "every citation and quote checks out" answer.
        "fully_grounded": 1 if trust.state == "verified" else 0,
        "quote_unverified": 1 if trust.quote_mutation_count else 0,
    }


def aggregate_faithfulness(rows: list[dict]) -> dict:
    """Aggregate per-answer faithfulness dicts into headline rates + a state
    distribution.

    ``rows`` are the dicts from :func:`compute_faithfulness`; falsy entries
    (skipped/errored questions that produced no answer) are dropped. Returns
    ``{}`` when nothing is measurable so the report can show "N/A" rather than a
    misleading 0.

    ``citation_grounding_rate`` is a ratio of sums (an answer that cites ten
    sources weights ten citations, not one), while the per-answer means are left
    to the generic :func:`eval.retrieval_metrics.aggregate` when needed.
    """
    rows = [r for r in rows if r]
    if not rows:
        return {}

    total_citations = sum(r["citation_count"] for r in rows)
    grounded_citations = sum(r["citations_grounded"] for r in rows)
    answers_with_citations = sum(r["has_citations"] for r in rows)
    fully_grounded = sum(r["fully_grounded"] for r in rows)

    distribution = dict.fromkeys(TRUST_STATES, 0)
    for r in rows:
        state = r["trust_state"]
        distribution[state] = distribution.get(state, 0) + 1

    return {
        "num_answers": len(rows),
        # Fraction of all emitted citations that survived the guard unmutated.
        "citation_grounding_rate": (
            grounded_citations / total_citations if total_citations else None
        ),
        # Among answers that cite at all, the fraction fully verified (no
        # citation or quote mutation) — the headline "每一句都能点回原典" number.
        "verified_rate_of_cited": (
            fully_grounded / answers_with_citations if answers_with_citations else None
        ),
        "answers_with_unverified_quote": sum(r["quote_unverified"] for r in rows),
        "total_citations": total_citations,
        "answers_with_citations": answers_with_citations,
        "state_distribution": distribution,
    }


def detect_faithfulness_regressions(
    current: dict, baseline: dict, tolerance: float = 0.02
) -> list[str]:
    """Grounding rates that dropped from ``baseline`` by more than ``tolerance``.

    Mirrors :func:`eval.retrieval_metrics.detect_regressions` but over the
    faithfulness rates. A ``None`` rate (nothing to measure on one side) is
    skipped rather than treated as a drop to zero.
    """
    regressions: list[str] = []
    for key in _GATED_RATES:
        cur_val = current.get(key)
        base_val = baseline.get(key)
        if not isinstance(cur_val, int | float) or not isinstance(base_val, int | float):
            continue
        if base_val - cur_val > tolerance:
            regressions.append(
                f"{key}: {cur_val:.3f} < baseline {base_val:.3f} (Δ {cur_val - base_val:+.3f})"
            )
    return regressions
