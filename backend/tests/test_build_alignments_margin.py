"""Tests for the margin-based candidate router in scripts/build_alignments.py.

Pure-logic tests only (no DB / LLM), mirroring the style of
test_alignment_flywheel.py: exercise the candidate-selection decision without
the corpus DB. Covers the two pure functions the process_pair() router is built
on — margin_score (the ratio-margin math) and classify_candidate (the 3-band
router) — plus the default-off / safety invariants the rollout depends on.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_alignments.py"
_spec = importlib.util.spec_from_file_location("build_alignments", _SCRIPT_PATH)
ba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ba)


# ── module constants (defaults are load-bearing for the safety guarantee) ──


class TestDefaultConstants:
    def test_default_values(self):
        assert ba.MARGIN_TOPK == 5
        assert ba.MARGIN_COSINE_FLOOR == 0.35
        assert ba.MARGIN_AUTO_ACCEPT == 999.0        # effectively DISABLED
        assert ba.MARGIN_AUTO_REJECT == 1.02
        # auto-accept also needs a strong absolute cosine (the no-LLM gate)
        assert ba.MARGIN_COSINE_FLOOR < ba.MARGIN_ACCEPT_MIN_COSINE

    def test_auto_accept_is_unreachable_by_default(self):
        # margin is a bounded ratio ~[1.0, K]; a 999.0 accept threshold can
        # never be met, so auto-accept is off unless an operator lowers it.
        assert ba.MARGIN_AUTO_ACCEPT > 100.0


# ── margin_score: best / mean(top-k) ───────────────────────────────────────


class TestMarginScore:
    def test_normal_dominant_top(self):
        # mean(top5) = 2.3/5 = 0.46; margin = 0.9 / 0.46
        scores = [0.9, 0.5, 0.4, 0.3, 0.2]
        assert ba.margin_score(scores) == pytest.approx(0.9 / 0.46)

    def test_single_candidate_is_unity(self):
        assert ba.margin_score([0.8]) == pytest.approx(1.0)

    def test_empty_is_zero(self):
        assert ba.margin_score([]) == 0.0

    def test_all_equal_is_unity(self):
        assert ba.margin_score([0.5, 0.5, 0.5, 0.5, 0.5]) == pytest.approx(1.0)

    def test_zero_mean_is_zero_not_div_by_zero(self):
        assert ba.margin_score([0.0, 0.0, 0.0]) == 0.0

    def test_negative_mean_is_zero(self):
        # non-positive mean short-circuits to 0.0 (never divides by zero)
        assert ba.margin_score([-0.1, -0.2, -0.3]) == 0.0

    def test_topk_clamps_to_available(self):
        # only 2 scores, default top_k=5 → denominator averages just those 2
        assert ba.margin_score([0.9, 0.5]) == pytest.approx(0.9 / 0.7)

    def test_topk_override_changes_denominator(self):
        scores = [0.9, 0.5, 0.4]
        assert ba.margin_score(scores, top_k=2) == pytest.approx(0.9 / 0.7)   # mean(0.9,0.5)
        assert ba.margin_score(scores, top_k=3) == pytest.approx(0.9 / 0.6)   # mean(0.9,0.5,0.4)

    def test_topk_zero_is_zero(self):
        assert ba.margin_score([0.9, 0.5], top_k=0) == 0.0

    def test_result_never_below_one_for_positive_scores(self):
        # with best-first input, best == max(top-k) >= mean(top-k) → margin >= 1.0
        assert ba.margin_score([0.9, 0.5, 0.4]) >= 1.0


# ── classify_candidate: 3-band router (total + mutually exclusive) ──────────


def _classify(best, margin, *, accept=1.30, reject=1.02, floor=0.35):
    return ba.classify_candidate(
        best, margin, accept_margin=accept, reject_margin=reject, cosine_floor=floor,
    )


class TestClassifyCandidate:
    # -- band 1: cosine floor --
    def test_below_floor_auto_rejects_even_with_huge_margin(self):
        assert _classify(0.30, margin=50.0) == "auto_reject"

    def test_exactly_at_floor_is_not_floor_rejected(self):
        # best == floor passes band 1 (>=); with a mid-band margin → llm_verify
        assert _classify(0.35, margin=1.10) == "llm_verify"

    # -- band 2: auto-accept (margin >= accept AND best >= MARGIN_ACCEPT_MIN_COSINE) --
    def test_auto_accept_at_margin_boundary(self):
        best = ba.MARGIN_ACCEPT_MIN_COSINE + 0.1
        assert _classify(best, margin=1.30, accept=1.30) == "auto_accept"      # margin == accept (inclusive)
        assert _classify(best, margin=1.2999, accept=1.30) == "llm_verify"     # just below → not accepted

    def test_auto_accept_needs_healthy_absolute_cosine(self):
        # margin clears accept, but best is just under MARGIN_ACCEPT_MIN_COSINE
        best = ba.MARGIN_ACCEPT_MIN_COSINE - 0.01
        assert _classify(best, margin=2.0, accept=1.30) == "llm_verify"
        # at the min-cosine boundary (inclusive) it flips to accept
        assert _classify(ba.MARGIN_ACCEPT_MIN_COSINE, margin=2.0, accept=1.30) == "auto_accept"

    # -- band 3: auto-reject (margin < reject) --
    def test_auto_reject_at_margin_boundary(self):
        best = 0.60
        assert _classify(best, margin=1.019, reject=1.02) == "auto_reject"     # below reject
        assert _classify(best, margin=1.02, reject=1.02) == "llm_verify"       # == reject (strict <) → verify

    # -- band 4: llm_verify (the mid band) --
    def test_mid_band_verifies(self):
        assert _classify(0.60, margin=1.15, accept=1.30, reject=1.02) == "llm_verify"

    # -- precedence: accept evaluated before reject (deterministic even if misconfigured) --
    def test_accept_wins_over_reject_when_misconfigured(self):
        # accept < reject: margin sits above accept but below reject → accept wins
        band = _classify(0.60, margin=1.20, accept=1.00, reject=1.50)
        assert band == "auto_accept"

    def test_every_input_maps_to_exactly_one_band(self):
        for best in (0.0, 0.34, 0.35, 0.5, 0.9):
            for margin in (0.0, 1.0, 1.01, 1.02, 1.3, 5.0, 999.0):
                assert _classify(best, margin) in {"auto_accept", "llm_verify", "auto_reject"}


# ── default-off / safety invariants (what the curated-quality guarantee needs) ──


class TestDefaultRoutingSafety:
    def _default_classify(self, best, margin):
        return ba.classify_candidate(
            best, margin,
            accept_margin=ba.MARGIN_AUTO_ACCEPT,
            reject_margin=ba.MARGIN_AUTO_REJECT,
            cosine_floor=ba.MARGIN_COSINE_FLOOR,
        )

    def test_strong_but_normal_candidate_routes_to_llm_verify(self):
        # a strong candidate (dominant margin, healthy cosine) still goes to the
        # LLM under defaults — auto-accept is OFF, so precision is preserved.
        assert self._default_classify(0.60, margin=1.20) == "llm_verify"

    def test_even_extreme_realistic_margin_never_auto_accepts_by_default(self):
        # margin 5.0 is enormous for real recall, yet 5.0 < 999.0 → still verify
        assert self._default_classify(0.80, margin=5.0) == "llm_verify"

    def test_below_floor_always_auto_rejects_by_default(self):
        assert self._default_classify(0.34, margin=999.0) == "auto_reject"
        assert self._default_classify(0.0, margin=1.5) == "auto_reject"

    def test_low_margin_auto_rejects_before_llm_by_default(self):
        # margin below 1.02 (no clear winner) is dropped before any LLM spend
        assert self._default_classify(0.60, margin=1.01) == "auto_reject"

    def test_margin_reject_one_disables_the_reject_band(self):
        # operator escape hatch: --margin-reject 1.0 → margin >= 1.0 always, so
        # nothing is margin-rejected → flat-floor behaviour (everything verifies)
        band = ba.classify_candidate(
            0.60, margin=1.001,
            accept_margin=ba.MARGIN_AUTO_ACCEPT,
            reject_margin=1.0,
            cosine_floor=ba.MARGIN_COSINE_FLOOR,
        )
        assert band == "llm_verify"
