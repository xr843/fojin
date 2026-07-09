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


# A chunk long enough to hold a quote at or above MIN_QUOTE_CHARS (12), so a
# test can exercise a quote the verifier actually checks rather than one it
# skips as too short to distinguish from normalisation noise.
_LONG_CHUNK = "舍利子，色不异空，空不异色，色即是空，空即是色。"


def _src(title: str = "心经", juan: int = 1, chunk_text: str = "色不异空，空不异色。") -> ChatSource:
    return ChatSource(
        text_id=7,
        juan_num=juan,
        chunk_index=0,
        chunk_text=chunk_text,
        score=0.9,
        title_zh=title,
    )


def test_clean_answer_with_a_checked_quote_is_fully_grounded():
    """The positive case: a citation *and* a verbatim quote the verifier checked.

    This test used to pass the answer "见【《心经》第1卷】。" — a citation with no
    quote at all — and assert ``fully_grounded == 1``. It was asserting the
    vacuous pass: zero quote mutations because zero quotes were examined. The
    quote below is 14 chars, above MIN_QUOTE_CHARS, so it is actually verified.
    """
    row = compute_faithfulness(
        "经云：「色不异空，空不异色，色即是空」【《心经》第1卷】",
        [_src(chunk_text=_LONG_CHUNK)],
    )
    assert row["trust_state"] == "verified"
    assert row["citation_count"] == 1
    assert row["citation_mutations"] == 0
    assert row["quote_count"] == 1
    assert row["fully_grounded"] == 1
    assert row["citations_grounded"] == 1


def test_citation_without_a_quote_keeps_the_badge_but_not_the_metric():
    """The user-facing trust badge and the eval gauge deliberately diverge here.

    ``trust_state`` stays ``verified`` (nothing the answer served is false — it
    cited a real source and misquoted nothing), but ``fully_grounded`` is 0
    because no quote was ever checked. Conflating the two is what let the gauge
    reward a model for quoting the canon less."""
    row = compute_faithfulness("见【《心经》第1卷】。", [_src()])
    assert row["trust_state"] == "verified"
    assert row["quote_count"] == 0
    assert row["fully_grounded"] == 0


def test_hallucinated_title_counts_as_corrected_not_grounded():
    # 大般若經 was never retrieved (only 心经 is in scope) → guard strips it.
    row = compute_faithfulness("见【《大般若經》第600卷】。", [_src()])
    assert row["trust_state"] == "citation_corrected"
    assert row["citation_mutations"] == 1
    assert row["citations_grounded"] == 0
    assert row["fully_grounded"] == 0


def test_fabricated_quote_is_downgraded_and_served_trustworthy():
    # Real citation, invented ≥12-char quote absent from the cited chunk →
    # verify_quoted_content downgrades it, so the served answer is honest:
    # trust=quote_relaxed, NOT verified (a quote was relaxed), but it counts as
    # served_trustworthy (no misrepresentation remains).
    answer = "经云：「假引文假引文假引文假引文」【《心经》第1卷】"
    row = compute_faithfulness(answer, [_src()])
    assert row["trust_state"] == "quote_relaxed"
    assert row["quotes_downgraded"] >= 1
    assert row["fully_grounded"] == 0            # not strictly verified
    assert row["served_trustworthy"] == 1        # but honest as served


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


# ──────────────────────────────────────────────────────────────────────
# Vacuous pass: "no evidence" was being scored as "evidence checked out"
#
# `verified` only means "≥1 citation and zero mutations". An answer that cites
# a source but quotes nothing has zero quote mutations vacuously, so it scored
# as fully grounded. Replaying 537 prod answers, 124 of 202 `verified` answers
# contained no checkable quote at all — and the metric rewards a model for
# quoting the canon *less*, which is the opposite of what fojin sells.
# ──────────────────────────────────────────────────────────────────────


def test_answer_that_cites_but_never_quotes_is_not_fully_grounded():
    """Citing a source without quoting it is honest, but nothing was verified."""
    row = compute_faithfulness("本经讲的是空性的道理【《心经》第1卷】。", [_src()])
    assert row["citation_count"] == 1
    assert row["quote_count"] == 0
    assert row["fully_grounded"] == 0


def test_quote_below_min_length_is_not_checked_and_not_fully_grounded():
    """MIN_QUOTE_CHARS exists because short fragments are normalisation noise.
    A sub-threshold quote is therefore *unverified*, not *verified* — the same
    absence-of-evidence the vacuous pass turned into a pass."""
    row = compute_faithfulness("经云：「色不异空」【《心经》第1卷】", [_src()])
    assert row["quote_count"] == 0
    assert row["fully_grounded"] == 0


def test_verbatim_quote_rate_denominator_is_answers_that_quoted():
    """Answers that never quoted must not dilute the quote-fidelity rate."""
    src = _src(chunk_text=_LONG_CHUNK)
    quoted_ok = compute_faithfulness(
        "经云：「色不异空，空不异色，色即是空」【《心经》第1卷】", [src]
    )
    quoted_bad = compute_faithfulness(
        "经云：「五阴覆盖般若灵明，使众生心识昏蒙」【《心经》第1卷】", [src]
    )
    never_quoted = compute_faithfulness("本经讲的是空性的道理【《心经》第1卷】。", [src])

    agg = aggregate_faithfulness([quoted_ok, quoted_bad, never_quoted])
    assert agg["answers_with_quotes"] == 2
    assert agg["verbatim_quote_rate"] == 0.5      # 1 of the 2 that quoted
    # …and the citation-level rate sees all three.
    assert agg["answers_with_citations"] == 3


def test_a_drop_in_verbatim_quote_rate_is_a_regression():
    """The new quote-fidelity number must gate, not merely decorate the report."""
    regressions = detect_faithfulness_regressions(
        {"verbatim_quote_rate": 0.30},
        {"verbatim_quote_rate": 0.50},
        tolerance=0.02,
    )
    assert any("verbatim_quote_rate" in r for r in regressions)


# ──────────────────────────────────────────────────────────────────────
# The report is where a human reads these numbers. A metric that exists
# only in the aggregate dict — and in the regression gate — is invisible
# to the person deciding what to work on next. verbatim_quote_rate was
# added in #953 and never rendered; the 2026-07-09 baseline had to be
# recomputed by hand from the raw JSON to read it.
# ──────────────────────────────────────────────────────────────────────


def test_report_renders_verbatim_quote_rate():
    from eval.run_eval import _faithfulness_section

    lines = _faithfulness_section(
        {
            "num_answers": 90,
            "answers_with_citations": 62,
            "answers_with_quotes": 53,
            "total_citations": 314,
            "citation_grounding_rate": 0.978,
            "verified_rate_of_cited": 0.484,
            "verbatim_quote_rate": 0.566,
            "served_trustworthy_rate": 0.968,
            "answers_with_downgraded_quote": 23,
            "state_distribution": {},
        }
    )
    body = "\n".join(lines)
    assert "verbatim_quote_rate" in body
    assert "56.6%" in body
    assert "53" in body          # answers_with_quotes, the honest denominator


def test_report_shows_na_when_no_answer_quoted():
    """verbatim_quote_rate is None when nothing quoted — render N/A, not 0%."""
    from eval.run_eval import _faithfulness_section

    lines = _faithfulness_section(
        {
            "num_answers": 5,
            "answers_with_citations": 3,
            "answers_with_quotes": 0,
            "verbatim_quote_rate": None,
            "citation_grounding_rate": 1.0,
            "verified_rate_of_cited": 0.0,
            "served_trustworthy_rate": 1.0,
            "total_citations": 3,
            "answers_with_downgraded_quote": 0,
            "state_distribution": {},
        }
    )
    body = "\n".join(lines)
    assert "N/A" in body
