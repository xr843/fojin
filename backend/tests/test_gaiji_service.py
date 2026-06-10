"""Unit tests for app.services.gaiji.

Tests use a hand-built ``GaijiNormalizer`` fixture rather than going
through ``build_normalizer`` and the DB — this PR is service-only,
DB integration is exercised in subsequent PRs.

Coverage:
- normalize_for_index: known composition / known PUA / unknown
  composition (preserved verbatim) / mixed text / nested-parens
  composition / empty text.
- expand_for_query: known glyph / multi-char (first char only) /
  unknown char / empty.
- Real-data smoke: the three CB00001-3 entries used as deploy
  sanity checks should round-trip through the small fixture.
"""
from __future__ import annotations

import pytest

from app.services.gaiji import (
    GaijiNormalizer,
    _COMPOSITION_RE,
    _PUA_TEXT_RE,
    expand_for_query,
    normalize_for_index,
)


@pytest.fixture
def normalizer() -> GaijiNormalizer:
    """Three real CBETA entries + one synthetic for unknown-comp coverage.

    CB00001: composition "[肄-聿+欠]", norm_big5 "款", PUA "U+F0001"
    CB00002: composition "[(匕/示)*頁]", norm_big5 "穎", PUA "U+F0002"
    CB00003: composition "[(工*刀)/言]", norm_big5 "辯", PUA "U+F0003"
    """
    return GaijiNormalizer(
        composition_to_norm={
            "[肄-聿+欠]": "款",
            "[(匕/示)*頁]": "穎",
            "[(工*刀)/言]": "辯",
        },
        pua_to_norm={
            "U+F0001": "款",
            "U+F0002": "穎",
            "U+F0003": "辯",
        },
        glyph_to_alternates={
            "款": frozenset({"[肄-聿+欠]", "U+F0001"}),
            "穎": frozenset({"[(匕/示)*頁]", "U+F0002"}),
            "辯": frozenset({"[(工*刀)/言]", "U+F0003"}),
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Regex shape


def test_composition_regex_matches_flat() -> None:
    assert _COMPOSITION_RE.findall("foo [木*奈] bar") == ["[木*奈]"]


def test_composition_regex_matches_nested_parens() -> None:
    """The hard case from CBETA: parentheses nest, but brackets don't."""
    sample = "[丮-(舉-與)+((乏-之+虫)/((乏-之+虫)*(乏-之+虫)))]"
    assert _COMPOSITION_RE.findall(sample) == [sample]


def test_composition_regex_does_not_match_empty_brackets() -> None:
    assert _COMPOSITION_RE.findall("text [] more") == []


def test_pua_regex_matches_textual_codepoint() -> None:
    assert _PUA_TEXT_RE.findall("see U+F0001 here") == ["U+F0001"]


def test_pua_regex_does_not_match_normal_unicode_codepoint() -> None:
    """U+4E2D (中) is BMP, not PUA — must not match."""
    assert _PUA_TEXT_RE.findall("char U+4E2D") == []


# ──────────────────────────────────────────────────────────────────────
# normalize_for_index


def test_normalize_replaces_known_composition(normalizer: GaijiNormalizer) -> None:
    assert normalize_for_index("佛说[肄-聿+欠]经", normalizer) == "佛说款经"


def test_normalize_replaces_known_pua(normalizer: GaijiNormalizer) -> None:
    assert normalize_for_index("see U+F0002 here", normalizer) == "see 穎 here"


def test_normalize_preserves_unknown_composition(normalizer: GaijiNormalizer) -> None:
    """A composition not in the table must round-trip unchanged."""
    text = "未知 [未*录] 字符"
    assert normalize_for_index(text, normalizer) == text


def test_normalize_handles_mixed_composition_and_pua(normalizer: GaijiNormalizer) -> None:
    assert (
        normalize_for_index("[肄-聿+欠]和U+F0003字符", normalizer)
        == "款和辯字符"
    )


def test_normalize_handles_multiple_compositions_in_one_line(
    normalizer: GaijiNormalizer,
) -> None:
    assert (
        normalize_for_index("[肄-聿+欠][(匕/示)*頁][(工*刀)/言]", normalizer)
        == "款穎辯"
    )


def test_normalize_passes_through_normal_text(normalizer: GaijiNormalizer) -> None:
    assert normalize_for_index("普通文本无缺字", normalizer) == "普通文本无缺字"


def test_normalize_empty_text(normalizer: GaijiNormalizer) -> None:
    assert normalize_for_index("", normalizer) == ""


# ──────────────────────────────────────────────────────────────────────
# expand_for_query


def test_expand_returns_known_alternates(normalizer: GaijiNormalizer) -> None:
    assert expand_for_query("款", normalizer) == frozenset(
        {"[肄-聿+欠]", "U+F0001"}
    )


def test_expand_unknown_glyph_returns_empty(normalizer: GaijiNormalizer) -> None:
    assert expand_for_query("佛", normalizer) == frozenset()


def test_expand_empty_token_returns_empty(normalizer: GaijiNormalizer) -> None:
    assert expand_for_query("", normalizer) == frozenset()


def test_expand_multi_char_uses_first_char_only(
    normalizer: GaijiNormalizer,
) -> None:
    """Multi-char tokens are gaiji-expanded char-by-char by the caller."""
    assert expand_for_query("款诉", normalizer) == frozenset(
        {"[肄-聿+欠]", "U+F0001"}
    )


# ──────────────────────────────────────────────────────────────────────
# Diagnostics


def test_size_reports_total_distinct_entries(normalizer: GaijiNormalizer) -> None:
    # 3 compositions + 3 PUAs
    assert normalizer.size() == 6
