"""Tests for recovering citations the model quoted from memory but never marked.

``eval/recover_citations.py`` asks: when an answer quotes real canon without a
``【《经名》第N卷】`` marker, can we name the text and fascicle after the fact?

Only the ranking/aggregation logic is pure and testable here; the Elasticsearch
recall step needs the prod index, like the rest of the eval harness. What CI can
protect is that 正藏 outranks 續藏 the same way the retrieval path ranks it, that
an ambiguous passage is reported as ambiguous rather than silently resolved to
whichever text sorted first, and that the rates use the denominators they claim.

Pure logic: no DB, no ES, no network — same tier as test_faithfulness.
"""

from eval.recover_citations import (
    Candidate,
    is_continued_canon,
    rank_candidates,
    resolution_of,
    summarise,
    score_outcome,
    summarise_control,
)


def _c(text_id: int, cbeta: str, title: str, juan: int = 1) -> Candidate:
    return Candidate(text_id=text_id, cbeta_id=cbeta, title_zh=title, juan_num=juan)


class TestContinuedCanonRule:
    def test_matches_the_rule_the_retrieval_path_uses(self):
        """Pin against ``rag_retrieval._is_continued_canon`` so the two cannot drift.

        Both answer "is this 卍續藏, i.e. almost certainly commentary". If the
        retrieval path ever changes its tiering rule, recovery must move with it
        or the two halves of the product will disagree about what a root text is.
        """
        from app.services.rag_retrieval import _is_continued_canon

        for cbeta in ("T0235", "X0123", "B07n0023", "G0001", "ZW10n0081", "", "J12"):
            assert is_continued_canon(cbeta) == _is_continued_canon({"cbeta_id": cbeta}), cbeta

    def test_x_prefix_is_the_only_continued_canon(self):
        assert is_continued_canon("X1600") is True
        assert is_continued_canon("T1564") is False
        assert is_continued_canon("") is False


class TestRankCandidates:
    def test_root_canon_outranks_commentary(self):
        """The 中论 三是偈 lives in 中論 itself and in dozens of 續藏 注疏.

        Naming a commentary as the source of a root-canon verse would hand the
        reader a citation that technically contains the words and is still the
        wrong provenance.
        """
        # The 續藏 entries deliberately carry the LOWER text_ids: if the canon
        # tier were dropped, the id tiebreak alone would put 中觀論疏 first, so
        # this fixture fails the moment the rule stops applying. (An earlier
        # version had T1564 at the lowest id and passed either way — a test that
        # asserted nothing.)
        ranked = rank_candidates([
            _c(100, "X0708", "中觀論疏"),
            _c(900, "T1564", "中論"),
            _c(101, "X0709", "中論疏記"),
        ])
        assert ranked[0].cbeta_id == "T1564"
        assert [c.cbeta_id for c in ranked] == ["T1564", "X0708", "X0709"]

    def test_ties_break_deterministically(self):
        """Two runs over the same answer must name the same 出处.

        ES hit order is not stable across queries; without a total order the
        recovered citation could flip between runs and the measured precision
        would be measuring the sort, not the method.
        """
        a = rank_candidates([_c(300, "T0251", "心經", 1), _c(100, "T0235", "金剛經", 2)])
        b = rank_candidates([_c(100, "T0235", "金剛經", 2), _c(300, "T0251", "心經", 1)])
        assert [c.text_id for c in a] == [c.text_id for c in b]


class TestResolutionOf:
    def test_a_single_root_text_resolves_uniquely(self):
        r = resolution_of([_c(100, "T1564", "中論", 3)])
        assert r["resolved"] is True
        assert r["unique_text"] is True
        assert r["best"].title_zh == "中論"
        assert r["best"].juan_num == 3

    def test_a_passage_in_many_texts_resolves_but_is_flagged_ambiguous(self):
        """Resolvable and unambiguous are different questions, and both matter.

        A verse quoted by forty commentaries is still attributable to its root
        text — but a reader deserves to know the passage is not unique to it, and
        the recovery rate would be dishonest if it counted this the same as a
        hapax.
        """
        r = resolution_of([
            _c(100, "T1564", "中論", 4),
            _c(900, "X0708", "中觀論疏", 9),
            _c(901, "X0709", "中論疏記", 2),
        ])
        assert r["resolved"] is True
        assert r["unique_text"] is False
        assert r["n_texts"] == 3
        assert r["best"].cbeta_id == "T1564"

    def test_nothing_found_is_unresolved_with_no_best_guess(self):
        r = resolution_of([])
        assert r["resolved"] is False
        assert r["best"] is None
        assert r["n_texts"] == 0

    def test_same_text_two_fascicles_is_one_text_but_two_candidates(self):
        """A passage repeated across 卷 of one 经 is not cross-text ambiguity.

        Counting it as two texts would understate the unique-resolution rate;
        the fascicle still has to be picked, so it stays two candidates.
        """
        r = resolution_of([_c(100, "T0220", "大般若經", 401), _c(100, "T0220", "大般若經", 402)])
        assert r["unique_text"] is True
        assert r["n_texts"] == 1
        assert r["n_candidates"] == 2


class TestSummarise:
    def test_rates_use_the_denominators_they_claim(self):
        rows = [
            {"resolved": True, "unique_text": True, "n_texts": 1, "n_candidates": 1},
            {"resolved": True, "unique_text": False, "n_texts": 5, "n_candidates": 7},
            {"resolved": False, "unique_text": False, "n_texts": 0, "n_candidates": 0},
            {"resolved": False, "unique_text": False, "n_texts": 0, "n_candidates": 0},
        ]
        s = summarise(rows)
        assert s["quotes"] == 4
        assert s["recovered"] == 2
        assert s["recovery_rate"] == 0.5
        # Unique is denominated in *recovered* quotes: "when we do name a text,
        # how often is it the only one" — pooling in the unrecovered would
        # conflate two different failures.
        assert s["unique_rate"] == 0.5

    def test_empty_run_is_unmeasurable_not_zero(self):
        assert summarise([]) == {}

    def test_nothing_recovered_leaves_unique_rate_unmeasured(self):
        s = summarise([{"resolved": False, "unique_text": False, "n_texts": 0, "n_candidates": 0}])
        assert s["recovery_rate"] == 0.0
        assert s["unique_rate"] is None


class TestSummariseControl:
    """The pooled precision is the number that must never stand alone."""

    def _o(self, unique, title_ok, juan_ok=None):
        return {"unique_text": unique, "title_ok": title_ok,
                "juan_ok": title_ok if juan_ok is None else juan_ok}

    def test_splits_precision_by_whether_the_passage_resolved_uniquely(self):
        """Measured 2026-09-02: pooled 81% averaged 96.3% and 40.0%.

        The pooled figure describes neither population, and the ship/no-ship
        decision rests entirely on the unique bucket — so the split has to be
        structural, not something a reader is trusted to compute.
        """
        outcomes = [self._o(True, True)] * 9 + [self._o(True, False)]
        outcomes += [self._o(False, True)] * 2 + [self._o(False, False)] * 3
        s = summarise_control(outcomes, sampled=20, available=100)
        assert s["unique"]["n"] == 10
        assert s["unique"]["title_precision"] == 0.9
        assert s["ambiguous"]["n"] == 5
        assert s["ambiguous"]["title_precision"] == 0.4
        assert s["pooled"]["n"] == 15
        assert s["pooled"]["title_precision"] == 11 / 15
        # The pooled value must lie strictly between the two — i.e. it is not
        # equal to either population it claims to summarise.
        assert s["ambiguous"]["title_precision"] < s["pooled"]["title_precision"] < s["unique"]["title_precision"]

    def test_found_rate_is_denominated_in_what_was_sampled_not_what_was_found(self):
        """Quotes the resolver could not locate must drag the found rate down.

        Denominating in located quotes would report 100% recall forever — the
        same vacuous-pass shape as scoring an answer that never quoted.
        """
        s = summarise_control([self._o(True, True)] * 3, sampled=10, available=50)
        assert s["found_rate"] == 0.3

    def test_nothing_located_reports_a_zero_found_rate_not_an_empty_dict(self):
        s = summarise_control([], sampled=40, available=90)
        assert s["found_rate"] == 0.0
        assert s["sampled"] == 40


class TestScoreOutcome:
    """Grading one recovery against the model's own citation."""

    def test_a_right_fascicle_under_the_wrong_text_does_not_count(self):
        """A 卷号 cannot be correct while its 经 is wrong.

        《心經》第1卷 and 《金剛經》第1卷 share a fascicle number and nothing else.
        Letting juan_ok float free of title_ok would score this as a fascicle
        hit and inflate the only precision figure the ship decision rests on.
        """
        r = resolution_of([_c(100, "T0235", "金剛經", 1)])
        o = score_outcome(r, cited_title="心經", cited_juan=1)
        assert o["title_ok"] is False
        assert o["juan_ok"] is False

    def test_traditional_and_simplified_titles_are_the_same_title(self):
        r = resolution_of([_c(100, "T1564", "中論", 4)])
        assert score_outcome(r, cited_title="中论", cited_juan=4)["title_ok"] is True

    def test_right_text_wrong_fascicle_scores_the_title_only(self):
        r = resolution_of([_c(100, "T1564", "中論", 4)])
        o = score_outcome(r, cited_title="中論", cited_juan=9)
        assert o["title_ok"] is True
        assert o["juan_ok"] is False

    def test_an_uncited_fascicle_cannot_score_a_fascicle_hit(self):
        r = resolution_of([_c(100, "T1564", "中論", 4)])
        assert score_outcome(r, cited_title="中論", cited_juan=None)["juan_ok"] is False

    def test_nothing_resolved_grades_as_a_miss_rather_than_raising(self):
        o = score_outcome(resolution_of([]), cited_title="中論", cited_juan=1)
        assert o == {"unique_text": False, "title_ok": False, "juan_ok": False}
