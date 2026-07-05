"""Tests for the deterministic citation-faithfulness eval metric.

The metric replays the production trust pipeline (citation guard → quote
verifier → trust status) over an ``(answer, sources)`` pair, so these tests
assert that each production failure mode maps to the trust state the eval will
report — and that the run-level aggregate + regression detector behave.

Pure logic: no DB, no LLM, no network — same tier as test_retrieval_metrics.
"""

from eval.faithfulness import (
    aggregate_faithfulness,
    compute_faithfulness,
    detect_faithfulness_regressions,
)

from app.schemas.chat import ChatSource


def _src(title: str = "心经", juan: int = 1) -> ChatSource:
    return ChatSource(
        text_id=7,
        juan_num=juan,
        chunk_index=0,
        chunk_text="色不异空，空不异色。",
        score=0.9,
        title_zh=title,
    )


def test_clean_answer_is_fully_grounded():
    row = compute_faithfulness("见【《心经》第1卷】。", [_src()])
    assert row["trust_state"] == "verified"
    assert row["citation_count"] == 1
    assert row["citation_mutations"] == 0
    assert row["fully_grounded"] == 1
    assert row["citations_grounded"] == 1


def test_hallucinated_title_counts_as_corrected_not_grounded():
    # 大般若經 was never retrieved (only 心经 is in scope) → guard strips it.
    row = compute_faithfulness("见【《大般若經》第600卷】。", [_src()])
    assert row["trust_state"] == "citation_corrected"
    assert row["citation_mutations"] == 1
    assert row["citations_grounded"] == 0
    assert row["fully_grounded"] == 0


def test_fabricated_quote_counts_as_quote_unverified():
    # Real citation, invented ≥12-char quote absent from the cited chunk.
    answer = "经云：「假引文假引文假引文假引文」【《心经》第1卷】"
    row = compute_faithfulness(answer, [_src()])
    assert row["trust_state"] == "quote_unverified"
    assert row["quote_mutations"] >= 1
    assert row["quote_unverified"] == 1
    assert row["fully_grounded"] == 0


def test_no_sources_is_ungrounded():
    row = compute_faithfulness("可参看《心经》【《心经》第1卷】。", [])
    assert row["trust_state"] == "no_sources"
    assert row["has_citations"] == 1
    assert row["fully_grounded"] == 0


def test_aggregate_uses_ratio_of_sums_and_state_distribution():
    rows = [
        {  # verified, 1 grounded citation
            "trust_state": "verified", "citation_count": 1, "citation_mutations": 0,
            "quote_mutations": 0, "citations_grounded": 1, "has_citations": 1,
            "fully_grounded": 1, "quote_unverified": 0,
        },
        {  # citation corrected, its 1 citation is not grounded
            "trust_state": "citation_corrected", "citation_count": 1, "citation_mutations": 1,
            "quote_mutations": 0, "citations_grounded": 0, "has_citations": 1,
            "fully_grounded": 0, "quote_unverified": 0,
        },
        {  # answer with sources but no citation at all
            "trust_state": "sources_available", "citation_count": 0, "citation_mutations": 0,
            "quote_mutations": 0, "citations_grounded": 0, "has_citations": 0,
            "fully_grounded": 0, "quote_unverified": 0,
        },
    ]
    agg = aggregate_faithfulness(rows)
    assert agg["num_answers"] == 3
    assert agg["total_citations"] == 2
    # 1 of 2 emitted citations survived the guard.
    assert agg["citation_grounding_rate"] == 0.5
    # 1 of 2 citing answers is fully verified (the no-citation answer excluded).
    assert agg["verified_rate_of_cited"] == 0.5
    assert agg["state_distribution"]["verified"] == 1
    assert agg["state_distribution"]["citation_corrected"] == 1
    assert agg["state_distribution"]["sources_available"] == 1
    assert agg["state_distribution"]["no_sources"] == 0


def test_aggregate_empty_and_none_rows_yield_no_data():
    assert aggregate_faithfulness([]) == {}
    # --no-llm / errored questions contribute None and must not crash or count.
    assert aggregate_faithfulness([None, None]) == {}


def test_aggregate_rates_are_none_when_no_citations():
    rows = [{
        "trust_state": "sources_available", "citation_count": 0, "citation_mutations": 0,
        "quote_mutations": 0, "citations_grounded": 0, "has_citations": 0,
        "fully_grounded": 0, "quote_unverified": 0,
    }]
    agg = aggregate_faithfulness(rows)
    assert agg["citation_grounding_rate"] is None
    assert agg["verified_rate_of_cited"] is None


def test_detect_regressions_flags_only_drops_beyond_tolerance():
    current = {"citation_grounding_rate": 0.90, "verified_rate_of_cited": 0.80}
    baseline = {"citation_grounding_rate": 0.95, "verified_rate_of_cited": 0.81}
    regs = detect_faithfulness_regressions(current, baseline, tolerance=0.02)
    # citation rate dropped 0.05 (> tol); verified rate dropped 0.01 (within tol).
    assert len(regs) == 1
    assert "citation_grounding_rate" in regs[0]


def test_detect_regressions_skips_none_rates():
    current = {"citation_grounding_rate": None}
    baseline = {"citation_grounding_rate": 0.95}
    assert detect_faithfulness_regressions(current, baseline) == []
