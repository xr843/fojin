"""Tests for the --juans CLI spec parser in scripts/build_alignments.py.

Pure-logic tests (no DB / LLM): parse_juans turns a CLI slice spec into a
sorted, deduplicated juan list used to override pair.text_a_juan_filter.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_alignments.py"
_spec = importlib.util.spec_from_file_location("build_alignments", _SCRIPT_PATH)
ba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ba)


class TestParseJuans:
    def test_comma_list(self):
        assert ba.parse_juans("1,2,3") == [1, 2, 3]

    def test_single_value(self):
        assert ba.parse_juans("7") == [7]

    def test_range(self):
        assert ba.parse_juans("1-3") == [1, 2, 3]

    def test_mixed_range_and_list(self):
        assert ba.parse_juans("1-3,7,9-10") == [1, 2, 3, 7, 9, 10]

    def test_dedup_and_sort(self):
        assert ba.parse_juans("3,1,2-3,1") == [1, 2, 3]

    def test_whitespace_tolerated(self):
        assert ba.parse_juans(" 1 , 2 - 4 ") == [1, 2, 3, 4]

    def test_single_element_range_allowed(self):
        assert ba.parse_juans("5-5") == [5]

    def test_reversed_range_rejected(self):
        with pytest.raises(ValueError, match="reversed range"):
            ba.parse_juans("3-1")

    def test_empty_item_rejected(self):
        with pytest.raises(ValueError, match="empty item"):
            ba.parse_juans("1,,3")

    def test_non_numeric_rejected(self):
        with pytest.raises(ValueError):
            ba.parse_juans("1,foo")

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match=">= 1"):
            ba.parse_juans("0,1")

    def test_open_ended_range_rejected(self):
        with pytest.raises(ValueError, match="malformed range"):
            ba.parse_juans("1-")


class TestJuansPairGuard:
    def test_juans_with_all_pairs_exits(self):
        import asyncio

        # Guard fires before any DB / LLM access, so this is a pure-logic test.
        with pytest.raises(SystemExit) as exc_info:
            asyncio.run(
                ba.main_async(
                    "all", True, None, 0.5, 1.0, False, 10, juans=[1, 2]
                )
            )
        assert exc_info.value.code == 1
