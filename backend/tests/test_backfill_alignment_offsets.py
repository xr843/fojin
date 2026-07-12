"""Tests for the pure locate/normalize logic in scripts/backfill_alignment_offsets.py.

No DB: the offset-location functions (normalize_with_map, locate_span,
pick_content) are pure and are what decides which char anchors get written to
alignment_pairs, so they are pinned here with fixture strings — including the
ambiguity rule (a repeated needle is skipped, never guessed) and the
normalized-match offset mapping back into the ORIGINAL content.
"""

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_alignment_offsets.py"
_spec = importlib.util.spec_from_file_location("backfill_alignment_offsets", _SCRIPT_PATH)
bo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bo)


class TestNormalizeWithMap:
    def test_strips_punct_whitespace_latin_digits(self):
        norm, idx = bo.normalize_with_map("如是，我聞。ABC 123")
        assert norm == "如是我聞"
        # Each kept char maps back to its original index.
        assert idx == [0, 1, 3, 4]

    def test_empty_and_all_punct(self):
        assert bo.normalize_with_map("") == ("", [])
        assert bo.normalize_with_map("。，！？ 42abc") == ("", [])

    def test_map_roundtrip(self):
        s = "「爾時，世尊」告諸比丘"
        norm, idx = bo.normalize_with_map(s)
        assert "".join(s[i] for i in idx) == norm


class TestLocateSpan:
    def test_verbatim_unique(self):
        status, start, end = bo.locate_span("前文。如是我聞後文", "如是我聞")
        assert status == "verbatim"
        assert (start, end) == (3, 7)

    def test_verbatim_offsets_slice_back_to_needle(self):
        content = "序言：一時佛在舍衛國祇樹給孤獨園。"
        needle = "佛在舍衛國"
        status, start, end = bo.locate_span(content, needle)
        assert status == "verbatim"
        assert content[start:end] == needle

    def test_ambiguous_verbatim_is_skipped(self):
        # 爾時世尊-style formulae recur; anchoring to the first hit would be
        # silently wrong, so ambiguity must return no offsets.
        status, start, end = bo.locate_span("爾時世尊…中略…爾時世尊", "爾時世尊")
        assert status == "ambiguous"
        assert start is None and end is None

    def test_normalized_fallback_maps_to_original_offsets(self):
        content = "廣序。如是，我聞：一時。尾。"
        needle = "如是我聞"  # verbatim absent (content has inner punctuation)
        status, start, end = bo.locate_span(content, needle)
        assert status == "normalized"
        # Span covers the original text including its internal punctuation,
        # and the normalized slice equals the normalized needle.
        assert content[start] == "如" and content[end - 1] == "聞"
        assert bo.normalize_with_map(content[start:end])[0] == "如是我聞"

    def test_normalized_ambiguous_is_skipped(self):
        # Verbatim absent (punctuation inside both occurrences), normalized
        # match found twice → still ambiguous, still skipped.
        status, start, end = bo.locate_span("如是，我聞。又：如是；我聞", "如是我聞")
        assert status == "ambiguous"
        assert start is None

    def test_not_found(self):
        assert bo.locate_span("南無阿彌陀佛", "如是我聞") == ("not_found", None, None)

    def test_empty_inputs(self):
        assert bo.locate_span("", "如是我聞") == ("empty", None, None)
        assert bo.locate_span("如是我聞", "") == ("empty", None, None)
        # Needle that normalizes to nothing (punctuation-only chunk).
        assert bo.locate_span("如是我聞", "。。！！") == ("empty", None, None)

    def test_verbatim_preferred_over_normalized(self):
        # When the needle exists verbatim, offsets must be the exact slice,
        # not a looser normalized region.
        content = "x如是我聞x"
        status, start, end = bo.locate_span(content, "如是我聞")
        assert status == "verbatim"
        assert content[start:end] == "如是我聞"


class TestPickContent:
    def test_prefers_side_lang_row(self):
        rows = [("en", "english body"), ("pi", "pali body")]
        assert bo.pick_content(rows, "pi") == "pali body"

    def test_single_row_fallback_when_lang_missing(self):
        assert bo.pick_content([("lzh", "漢文")], "pi") == "漢文"
        assert bo.pick_content([("lzh", "漢文")], None) == "漢文"

    def test_multiple_rows_without_lang_match_is_refused(self):
        # Writing an offset without knowing WHICH content row it indexes would
        # be a corrupt anchor — must refuse, not guess.
        rows = [("en", "english"), ("pi", "pali")]
        assert bo.pick_content(rows, "bo") is None
        assert bo.pick_content(rows, None) is None

    def test_no_rows(self):
        assert bo.pick_content([], "lzh") is None
