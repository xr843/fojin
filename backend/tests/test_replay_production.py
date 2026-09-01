"""Tests for replaying stored production answers through the faithfulness pipeline.

``eval/replay_production.py`` reads answers that prod already generated
(``chat_messages.content`` + ``.sources``) and runs the same deterministic
guards ``eval/faithfulness.py`` runs — no LLM, because the answers already
exist. These tests cover the parts that are pure logic: deserialising what prod
actually stored, and folding a run's answers into rows + an aggregate.

The DB layer (which rows to fetch) is not covered here for the same reason
``run_eval`` isn't: it needs the prod corpus. What CI *can* protect is that a
malformed stored row can't take down a 1,400-answer run, and that answers which
skip verification stay visible in the output instead of vanishing.

Pure logic: no DB, no LLM, no network — same tier as test_faithfulness.
"""

import pytest

from eval.replay_production import (
    ServeRecord,
    StoredAnswer,
    aggregate_serve_records,
    coverage,
    parse_stored_sources,
    replay_answers,
)

from app.schemas.chat import ChatSource


_LONG_CHUNK = "舍利子，色不异空，空不异色，色即是空，空即是色。"

# The exact shape ``chat.py:_save_messages`` writes: ``[s.model_dump() for s in
# sources]``. Kept verbatim rather than trimmed to the fields under test —
# a fixture that only carries what the assertion reads is how a real defect
# hides (a stored key the parser chokes on would never appear here).
_STORED_SOURCE = {
    "text_id": 7,
    "juan_num": 1,
    "chunk_index": 0,
    "chunk_text": _LONG_CHUNK,
    "score": 0.87,
    "title_zh": "心经",
    "lang": "lzh",
    "source_id": 3,
    "parallel_chunks": [],
    "urn": "fojin:cbeta/T0251.1",
}


def _answer(msg_id: int, text: str, sources: list | None = None) -> StoredAnswer:
    return StoredAnswer(
        message_id=msg_id,
        created_at="2026-09-01T04:00:00+00:00",
        answer=text,
        sources=parse_stored_sources(sources if sources is not None else [_STORED_SOURCE]),
    )


class TestParseStoredSources:
    def test_parses_the_shape_production_actually_stores(self):
        parsed = parse_stored_sources([_STORED_SOURCE])
        assert len(parsed) == 1
        assert isinstance(parsed[0], ChatSource)
        assert parsed[0].title_zh == "心经"
        assert parsed[0].chunk_text == _LONG_CHUNK
        assert parsed[0].urn == "fojin:cbeta/T0251.1"

    def test_fills_defaults_for_rows_written_before_the_trilingual_fields(self):
        """History predating the lang/urn/parallel_chunks columns must still load.

        ``ChatSource`` gives those fields defaults precisely so stored chat
        history keeps deserialising; a replay that only handled today's shape
        would silently drop every older answer from the denominator.
        """
        legacy = {
            "text_id": 7,
            "juan_num": 1,
            "chunk_index": 0,
            "chunk_text": _LONG_CHUNK,
            "score": 0.5,
            "title_zh": "心经",
        }
        parsed = parse_stored_sources([legacy])
        assert len(parsed) == 1
        assert parsed[0].lang == "lzh"
        assert parsed[0].urn is None
        assert parsed[0].parallel_chunks == []

    @pytest.mark.parametrize("raw", [None, [], "null"])
    def test_absent_sources_become_an_empty_list(self, raw):
        assert parse_stored_sources(raw) == []

    def test_a_malformed_entry_is_dropped_without_losing_its_siblings(self):
        """One bad row must not abort the run.

        1,410 of 1,426 stored answers are arrays and 16 are JSON null; a single
        unparseable neighbour taking down the whole replay would make the tool
        useless exactly when history is messiest.
        """
        parsed = parse_stored_sources([_STORED_SOURCE, {"text_id": "not-an-int"}, "garbage"])
        assert len(parsed) == 1
        assert parsed[0].title_zh == "心经"


class TestReplayAnswers:
    def test_returns_one_row_per_answer_carrying_its_message_id(self):
        rows, agg = replay_answers([
            _answer(101, f"经云：「{_LONG_CHUNK}」【《心经》第1卷】"),
            _answer(102, "见【《心经》第1卷】。"),
        ])
        assert [r["message_id"] for r in rows] == [101, 102]
        assert agg["num_answers"] == 2

    def test_a_verbatim_quote_scores_as_grounded(self):
        rows, agg = replay_answers([
            _answer(1, f"经云：「{_LONG_CHUNK}」【《心经》第1卷】"),
        ])
        assert rows[0]["fully_grounded"] == 1
        assert agg["verbatim_quote_rate"] == 1.0

    def test_a_paraphrase_in_quote_marks_is_counted_against_verbatim_rate(self):
        """The failure mode the brand claim actually rests on.

        The quote is 14 chars (above MIN_QUOTE_CHARS) and cites a retrieved
        source, so the verifier really examines it — it just isn't in the chunk.
        """
        rows, agg = replay_answers([
            _answer(1, "经云：「五蕴皆空，一切苦厄悉皆远离度尽」【《心经》第1卷】"),
        ])
        assert rows[0]["quotes_downgraded"] >= 1
        assert agg["verbatim_quote_rate"] == 0.0

    def test_answers_that_skip_verification_stay_in_the_output(self):
        """The 32.2% coverage hole must be visible, not silently dropped.

        ``verify_quoted_content`` early-exits when the answer carries no
        ``【《`` marker, so these answers are never checked. They still have to
        appear in num_answers and the state distribution — otherwise the
        reported rates look like they cover everything, which is the exact
        misreading this whole exercise exists to stop.
        """
        rows, agg = replay_answers([
            _answer(1, f"经云：「{_LONG_CHUNK}」【《心经》第1卷】"),
            _answer(2, "五蕴是色受想行识五种聚合，出自心经。"),
        ])
        assert agg["num_answers"] == 2
        assert sum(agg["state_distribution"].values()) == 2
        assert rows[1]["has_citation_marker"] == 0
        assert rows[0]["has_citation_marker"] == 1

    def test_an_unmarked_answer_carries_its_quote_past_every_guard(self):
        """The coverage hole, stated as the defect it is rather than a caveat.

        ``verify_quoted_content`` early-exits on ``"【《" not in answer``, so an
        answer that puts canon in 「」 without a bracket citation is never
        examined. It reports zero quote mutations — not because the quote held
        up, but because nobody looked. 459 of 1,426 production answers over 30
        days (32.2%) take this path, and every faithfulness rate silently
        excludes them.

        This is the number step 2 of this work has to move, so it needs a test
        that fails the moment the early-exit stops applying.
        """
        unmarked = "经中说「五蕴皆空一切苦厄悉皆远离度尽无余」，此为要义。"
        rows, agg = replay_answers([_answer(1, unmarked)])
        assert rows[0]["has_citation_marker"] == 0
        # Zero mutations here means "unexamined", not "verified".
        assert rows[0]["quote_mutations"] == 0
        assert agg["verbatim_quote_rate"] is None

    def test_a_stripped_citation_still_counts_as_marked(self):
        """"Cited a text we never retrieved" is a different defect from "never cited".

        The guard strips the citation, but ``citation_count`` is read off the
        RAW answer (chat_trust.py:38), so this answer reports a citation *and* a
        mutation. It is inside the measured 68%, unlike the case above — which
        is why the marker flag, not ``answers_with_citations``, is what delimits
        the coverage hole.
        """
        rows, _ = replay_answers([
            _answer(1, "经云：「凡所有相皆是虚妄不实之法」【《金刚经》第1卷】"),
        ])
        assert rows[0]["has_citation_marker"] == 1
        assert rows[0]["citation_count"] == 1
        assert rows[0]["citation_mutations"] == 1

    def test_fascicle_resolver_is_threaded_through_to_the_juan_check(self):
        """The wrong-卷号 class of error is invisible to the runtime guards.

        ``quote_verifier._find_sources`` falls back to any fascicle of the cited
        text, so a quote that is verbatim in 卷2 passes while the answer says
        第1卷. Only compute_fascicle_accuracy consults text_contents and catches
        it — replay must pass the resolver down or that column reads N/A forever.
        """
        def juan_text(message_id: int, title: str, juan: int) -> str | None:
            return _LONG_CHUNK if juan == 2 else "别的卷的内容，完全不含所引之句。"

        _, agg = replay_answers(
            [_answer(1, f"经云：「{_LONG_CHUNK}」【《心经》第1卷】")],
            juan_text=juan_text,
        )
        assert agg["fascicle_checked"] == 1
        assert agg["fascicle_accuracy_rate"] == 0.0

    def test_the_resolver_is_scoped_per_answer_so_one_title_can_mean_two_texts(self):
        """The same 经名 legitimately resolves to different texts in different answers.

        PR #1209 landed on exactly this: 「楞伽经」 in search and in chat were two
        different 经. A resolver keyed only on (title, juan) would blur them and
        silently adjudicate one answer's citation against the other's fascicle,
        so the message id has to be part of the key.
        """
        seen: list[int] = []

        def juan_text(message_id: int, title: str, juan: int) -> str | None:
            seen.append(message_id)
            # 卷1 holds the quote only for message 2; message 1 cites the other 楞伽经.
            return _LONG_CHUNK if message_id == 2 else "另一部同名经的卷一，不含此句。"

        _, agg = replay_answers(
            [
                _answer(1, f"经云：「{_LONG_CHUNK}」【《楞伽经》第1卷】"),
                _answer(2, f"经云：「{_LONG_CHUNK}」【《楞伽经》第1卷】"),
            ],
            juan_text=juan_text,
        )
        assert seen == [1, 2]
        assert agg["fascicle_checked"] == 2
        assert agg["fascicle_accuracy_rate"] == 0.5

    def test_no_resolver_leaves_the_fascicle_column_unmeasured_rather_than_zero(self):
        _, agg = replay_answers([_answer(1, f"经云：「{_LONG_CHUNK}」【《心经》第1卷】")])
        assert agg["fascicle_checked"] == 0
        assert agg["fascicle_accuracy_rate"] is None

    def test_empty_run_aggregates_to_nothing_measurable(self):
        rows, agg = replay_answers([])
        assert rows == []
        assert agg == {}


class TestServeRecords:
    """The raw-answer truth, read from what the guards recorded at serve time."""

    def _rec(self, mid, *, state="verified", cites=1, cite_mut=0, quote_mut=0, checked=1):
        return ServeRecord(
            message_id=mid, trust_state=state, citation_count=cites,
            citation_mutations=cite_mut, quote_mutations=quote_mut, quote_checked=checked,
        )

    def test_verbatim_rate_is_denominated_in_answers_that_quoted(self):
        agg = aggregate_serve_records([
            self._rec(1),                              # quoted, clean
            self._rec(2, state="quote_relaxed", quote_mut=1),  # quoted, downgraded
            self._rec(3, checked=0),                   # cited but never quoted
        ])
        assert agg["answers_with_quotes"] == 2
        assert agg["verbatim_quote_rate"] == 0.5

    def test_citing_without_quoting_does_not_pass_vacuously(self):
        """An answer that cites a source and quotes none of it verified nothing.

        Scoring it 1 would let the model improve the metric by quoting less —
        the exact reward hack aggregate_faithfulness documents guarding against.
        """
        agg = aggregate_serve_records([self._rec(1, checked=0)])
        assert agg["answers_with_citations"] == 1
        assert agg["verified_rate_of_cited"] == 0.0
        assert agg["verbatim_quote_rate"] is None

    def test_grounding_rate_weights_by_citation_not_by_answer(self):
        agg = aggregate_serve_records([
            self._rec(1, cites=10, cite_mut=1, state="citation_corrected"),
            self._rec(2, cites=1),
        ])
        assert agg["total_citations"] == 11
        assert agg["citation_grounding_rate"] == 10 / 11

    def test_empty_run_is_unmeasurable_not_zero(self):
        assert aggregate_serve_records([]) == {}


class TestReplayCannotSubstituteForServeRecords:
    """Pins the 2026-09-01 defect so it cannot be "simplified" back in.

    The first version of this tool computed production faithfulness by replaying
    stored answers. It reported 100% on every rate. The stored answer is the
    *corrected* one: verify_quoted_content strips the quote marks off a
    non-verbatim quote, and says in its own docstring that a second pass is
    therefore a no-op. Replay measured a washed shirt and reported no dirt.
    """

    def test_an_already_downgraded_answer_replays_as_spotless(self):
        # What production stored after downgrading a paraphrase: the quote marks
        # are gone, the citation stayed. Nothing left for the verifier to catch.
        served = "经中说五蕴皆空一切苦厄悉皆远离度尽，见【《心经》第1卷】。"
        rows, replay_agg = replay_answers([_answer(1, served)])
        assert rows[0]["quote_mutations"] == 0
        assert rows[0]["quotes_downgraded"] == 0

        # The serve-time record of the SAME answer remembers the downgrade.
        serve_agg = aggregate_serve_records([
            ServeRecord(message_id=1, trust_state="quote_relaxed", citation_count=1,
                        citation_mutations=0, quote_mutations=1, quote_checked=1)
        ])
        assert serve_agg["verbatim_quote_rate"] == 0.0
        assert serve_agg["answers_with_downgraded_quote"] == 1

        # The two disagree by construction. Whenever they do, the serve record is
        # the one telling the truth about the model.
        assert replay_agg.get("verbatim_quote_rate") != serve_agg["verbatim_quote_rate"]


class TestCoverage:
    def test_counts_the_answers_the_verifier_declined_to_open(self):
        rows, _ = replay_answers([
            _answer(1, f"经云：「{_LONG_CHUNK}」【《心经》第1卷】"),
            _answer(2, "五蕴是色受想行识五种聚合。"),
            _answer(3, "另一条也没有标记。"),
        ])
        cov = coverage(rows)
        assert cov == {
            "answers": 3,
            "with_citation_marker": 1,
            "without_citation_marker": 2,
            "marker_rate": 1 / 3,
        }
