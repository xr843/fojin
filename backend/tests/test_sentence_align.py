"""Tests for the sentence-level alignment core (Package C).

Pure-function focus, no DB / no embedding API (mirrors the pure-logic style of
test_alignment_flywheel.py and the importlib script-loading of
test_backfill_alignment_offsets.py):

* split_sentences — offset correctness (Chinese punctuated / unpunctuated
  fallback / trailing text with no final punctuation / nested 「」 / leading
  whitespace / non-Chinese newline splitting) with offsets that map back into
  the source via base_offset;
* cosine_matrix — concrete values incl. zero-norm and orthogonal cells;
* align_sentences — synthetic matrices: perfect diagonal, a genuine 1-2 merge,
  a low-similarity pair dropped by min_similarity, a skip/gap case, empties;
* sentence_align_key / build_insert_rows — the uq_sentence_align idempotency
  helper and in-batch dedup;
* embed_and_align — the glue maps aligner indices back to offset spans.
"""

import importlib.util
from pathlib import Path

import pytest

from app.services.sentence_align import (
    AlignedPair,
    Sentence,
    align_sentences,
    cosine_matrix,
    embed_and_align,
    sentence_align_key,
    split_sentences,
)

# Load the batch script for its pure helpers (it is not an importable package).
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refine_sentence_alignments.py"
_spec = importlib.util.spec_from_file_location("refine_sentence_alignments", _SCRIPT_PATH)
refine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refine)


# ── split_sentences ─────────────────────────────────────────────────────────


class TestSplitChinese:
    def test_punctuated_offsets_and_trailing_punct(self):
        # 。 attaches to the sentence it ends; offsets slice back exactly.
        text = "如是我聞。一時佛在。"
        sents = split_sentences(text, "lzh")
        assert [(s.char_start, s.char_end, s.text) for s in sents] == [
            (0, 5, "如是我聞。"),
            (5, 10, "一時佛在。"),
        ]
        for s in sents:
            assert text[s.char_start:s.char_end] == s.text

    def test_base_offset_maps_into_juan(self):
        text = "如是我聞。一時佛在。"
        sents = split_sentences(text, "zh", base_offset=100)
        assert (sents[0].char_start, sents[0].char_end) == (100, 105)
        assert (sents[1].char_start, sents[1].char_end) == (105, 110)

    def test_unpunctuated_fallback_is_single_sentence(self):
        sents = split_sentences("南無阿彌陀佛", "lzh")
        assert len(sents) == 1
        assert (sents[0].char_start, sents[0].char_end, sents[0].text) == (0, 6, "南無阿彌陀佛")

    def test_trailing_text_without_final_punctuation(self):
        text = "如是我聞。世尊"
        sents = split_sentences(text, "lzh")
        assert [s.text for s in sents] == ["如是我聞。", "世尊"]
        assert (sents[1].char_start, sents[1].char_end) == (5, 7)

    def test_nested_quotes_close_attaches_not_splits_open(self):
        # Opening 「 never splits; the closing run 。」 attaches to the sentence.
        text = "佛言：「汝諦聽。」善哉。"
        sents = split_sentences(text, "lzh")
        assert [s.text for s in sents] == ["佛言：「汝諦聽。」", "善哉。"]
        assert (sents[0].char_start, sents[0].char_end) == (0, 9)

    def test_leading_whitespace_trimmed_but_offset_points_to_real_char(self):
        text = "  如是我聞。"
        sents = split_sentences(text, "lzh")
        assert len(sents) == 1
        assert sents[0].char_start == 2  # not 0 — leading spaces trimmed inward
        assert sents[0].text == "如是我聞。"
        assert text[sents[0].char_start:sents[0].char_end] == sents[0].text

    def test_semicolon_and_bang_question_terminate(self):
        text = "善哉！何以故？如是；"
        sents = split_sentences(text, "lzh")
        assert [s.text for s in sents] == ["善哉！", "何以故？", "如是；"]

    def test_whitespace_only_yields_nothing(self):
        assert split_sentences("   \n  ", "lzh") == []
        assert split_sentences("", "lzh") == []


class TestSplitOther:
    def test_latin_split_on_punct_and_newline(self):
        text = "Hello world. Is it?\nNew line"
        sents = split_sentences(text, "en")
        assert [s.text for s in sents] == ["Hello world.", "Is it?", "New line"]
        # Offsets slice back exactly through trimmed whitespace/newline.
        for s in sents:
            assert text[s.char_start:s.char_end] == s.text

    def test_pali_period_split(self):
        text = "evaṃ me sutaṃ. ekaṃ samayaṃ."
        sents = split_sentences(text, "pi")
        assert [s.text for s in sents] == ["evaṃ me sutaṃ.", "ekaṃ samayaṃ."]

    def test_consecutive_terminators_stay_together(self):
        sents = split_sentences("Really?! Yes.", "en")
        assert [s.text for s in sents] == ["Really?!", "Yes."]

    def test_blank_lines_collapse(self):
        text = "Aa.\n\n\nBb."
        sents = split_sentences(text, "en")
        assert [s.text for s in sents] == ["Aa.", "Bb."]

    def test_degenerate_fragments_dropped(self):
        # Bare punctuation and single-char stubs (the prod garbage: "。", "身。")
        # must be filtered — they produced spurious cross-lingual alignments.
        assert split_sentences("。", "lzh") == []
        assert split_sentences("身。", "lzh") == []
        # A real short verse line survives (≥2 content chars).
        assert [s.text for s in split_sentences("諸行無常。", "lzh")] == ["諸行無常。"]
        # Mixed: only the meaningful sentence is kept, the "。" stub is dropped.
        got = [s.text for s in split_sentences("身。諸行無常。", "lzh")]
        assert got == ["諸行無常。"]

    def test_degenerate_fragment_offsets_stay_exact(self):
        # Dropping a leading stub must not corrupt the surviving sentence's offsets.
        text = "身。諸行無常。"
        sents = split_sentences(text, "lzh", base_offset=100)
        assert len(sents) == 1
        s = sents[0]
        assert text[s.char_start - 100 : s.char_end - 100] == s.text


# ── cosine_matrix ───────────────────────────────────────────────────────────


class TestCosineMatrix:
    def test_identity_and_orthogonal(self):
        sim = cosine_matrix([[1.0, 0.0], [0.0, 1.0]], [[1.0, 0.0], [0.0, 1.0]])
        assert sim[0][0] == pytest.approx(1.0)
        assert sim[0][1] == pytest.approx(0.0)
        assert sim[1][0] == pytest.approx(0.0)
        assert sim[1][1] == pytest.approx(1.0)

    def test_non_unit_vectors_normalized(self):
        # cos(3,4 ; 3,4) == 1; cos(3,4 ; 4,-3) == 0 (orthogonal).
        sim = cosine_matrix([[3.0, 4.0]], [[3.0, 4.0], [4.0, -3.0]])
        assert sim[0][0] == pytest.approx(1.0)
        assert sim[0][1] == pytest.approx(0.0)

    def test_zero_norm_is_zero(self):
        sim = cosine_matrix([[0.0, 0.0]], [[1.0, 1.0]])
        assert sim[0][0] == 0.0

    def test_shape(self):
        sim = cosine_matrix([[1.0], [1.0], [1.0]], [[1.0], [1.0]])
        assert len(sim) == 3 and all(len(r) == 2 for r in sim)


# ── align_sentences ─────────────────────────────────────────────────────────


class TestAlignSentences:
    def test_perfect_diagonal_all_1_1(self):
        sim = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        out = align_sentences(sim)
        assert [(t, si, ti) for t, si, ti, _ in out] == [
            ("1-1", (0,), (0,)),
            ("1-1", (1,), (1,)),
            ("1-1", (2,), (2,)),
        ]
        assert all(score == pytest.approx(1.0) for *_, score in out)

    def test_genuine_1_2_merge(self):
        # One source sentence corresponds to two target sentences.
        sim = [[0.9, 0.85]]
        out = align_sentences(sim, gap_penalty=0.5, min_similarity=0.4)
        assert len(out) == 1
        align_type, src_idx, tgt_idx, score = out[0]
        assert align_type == "1-2"
        assert src_idx == (0,) and tgt_idx == (0, 1)
        assert score == pytest.approx(0.875)

    def test_genuine_2_1_merge(self):
        # Two source sentences correspond to one target sentence.
        sim = [[0.9], [0.85]]
        out = align_sentences(sim, gap_penalty=0.5, min_similarity=0.4)
        assert len(out) == 1
        align_type, src_idx, tgt_idx, score = out[0]
        assert align_type == "2-1"
        assert src_idx == (0, 1) and tgt_idx == (0,)
        assert score == pytest.approx(0.875)

    def test_low_similarity_pair_dropped(self):
        # DP lays down the diagonal; the (1,1) pair at 0.2 is below the cutoff.
        sim = [
            [0.9, 0.0],
            [0.1, 0.2],
        ]
        out = align_sentences(sim, gap_penalty=0.5, min_similarity=0.4)
        assert [(si, ti) for _, si, ti, _ in out] == [((0,), (0,))]

    def test_skip_gap_case(self):
        # src[1] matches nothing; the DP skips it rather than force a bad align.
        sim = [[0.9], [-0.5]]
        out = align_sentences(sim, gap_penalty=0.3, min_similarity=0.4)
        assert len(out) == 1
        assert out[0][:3] == ("1-1", (0,), (0,))

    def test_empty_inputs(self):
        assert align_sentences([]) == []
        assert align_sentences([[]]) == []
        assert align_sentences([[], []]) == []


# ── idempotency helpers ─────────────────────────────────────────────────────


class TestKeyAndDedup:
    def test_key_is_the_uq_tuple(self):
        assert sentence_align_key(1, 2, 3, 4, 5, 6) == (1, 2, 3, 4, 5, 6)

    def test_key_distinguishes_char_start(self):
        assert sentence_align_key(1, 2, 3, 4, 5, 6) != sentence_align_key(1, 2, 30, 4, 5, 6)

    def test_build_insert_rows_dedups_within_batch(self):
        seen: set = set()
        aligned = [
            AlignedPair("1-1", 0, 5, "甲。", 0, 4, "A.", 0.9),
            AlignedPair("1-1", 0, 5, "甲。", 0, 4, "A.", 0.9),  # same identity → dropped
            AlignedPair("1-1", 5, 9, "乙。", 4, 8, "B.", 0.8),
        ]
        rows = refine.build_insert_rows(
            source_pair_id=42,
            text_a_id=1, text_a_juan_num=1, text_a_lang="lzh",
            text_b_id=2, text_b_juan_num=1, text_b_lang="en",
            aligned=aligned, method="sentence-bertalign", seen=seen,
        )
        assert len(rows) == 2
        assert rows[0]["source_pair_id"] == 42
        assert rows[0]["text_a_char_start"] == 0 and rows[1]["text_a_char_start"] == 5
        assert rows[0]["align_type"] == "1-1"
        # seen carries across calls, so a re-emit of an existing pair is dropped.
        again = refine.build_insert_rows(
            source_pair_id=99,
            text_a_id=1, text_a_juan_num=1, text_a_lang="lzh",
            text_b_id=2, text_b_juan_num=1, text_b_lang="en",
            aligned=[aligned[0]], method="sentence-bertalign", seen=seen,
        )
        assert again == []


class TestScriptPureHelpers:
    def test_parse_method_filter(self):
        assert refine.parse_method_filter("embed_llm, manual ,expert") == ["embed_llm", "manual", "expert"]
        assert refine.parse_method_filter("") is None
        assert refine.parse_method_filter(None) is None
        assert refine.parse_method_filter(" , ") is None

    def test_pick_content_prefers_side_lang(self):
        rows = [("en", "english"), ("pi", "pali")]
        assert refine.pick_content(rows, "pi") == "pali"

    def test_pick_content_single_row_fallback(self):
        assert refine.pick_content([("lzh", "漢文")], "pi") == "漢文"

    def test_pick_content_ambiguous_refused(self):
        assert refine.pick_content([("en", "e"), ("pi", "p")], "bo") is None
        assert refine.pick_content([], "lzh") is None


# ── embed_and_align glue ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_embed_and_align_maps_offsets_back():
    src = [Sentence(0, 3, "abc"), Sentence(4, 7, "def")]
    tgt = [Sentence(10, 13, "ABC"), Sentence(14, 17, "DEF")]

    async def fake_embed(texts):
        # inputs order: src texts then tgt texts → [abc, def, ABC, DEF]
        table = {"abc": [1.0, 0.0], "def": [0.0, 1.0], "ABC": [1.0, 0.0], "DEF": [0.0, 1.0]}
        return [table[t] for t in texts]

    out = await embed_and_align(src, tgt, embed_fn=fake_embed)
    assert [(p.align_type, p.a_char_start, p.a_char_end, p.b_char_start, p.b_char_end) for p in out] == [
        ("1-1", 0, 3, 10, 13),
        ("1-1", 4, 7, 14, 17),
    ]
    assert out[0].sent_a_text == "abc" and out[0].sent_b_text == "ABC"
    assert out[0].similarity == pytest.approx(1.0)


@pytest.mark.anyio
async def test_embed_and_align_empty_side_returns_empty():
    async def fake_embed(texts):  # pragma: no cover - must not be called
        raise AssertionError("embed should not run for an empty side")

    assert await embed_and_align([], [Sentence(0, 1, "x")], embed_fn=fake_embed) == []
    assert await embed_and_align([Sentence(0, 1, "x")], [], embed_fn=fake_embed) == []
