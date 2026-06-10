"""Tests for the gaiji query-expansion glue in app.services.search.

Covers the _gaiji_should_clauses helper that turns a raw query string
into the OR-clauses added to the ES bool query so that searching "款"
also matches passages still encoded as "[肄-聿+欠]" or "U+F0001".
"""
from __future__ import annotations

import pytest

from app.services.gaiji import GaijiNormalizer
from app.services.search import _gaiji_should_clauses


@pytest.fixture
def normalizer() -> GaijiNormalizer:
    """Same three-entry fixture used by test_gaiji_service.py."""
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


def _alternates_in(clauses: list[dict]) -> set[str]:
    """Strip ES clause wrapping; return the bare alternate strings."""
    return {c["match_phrase"]["content"] for c in clauses}


def test_no_clauses_when_normalizer_is_none() -> None:
    assert _gaiji_should_clauses("款", None) == []


def test_no_clauses_when_query_is_empty(normalizer: GaijiNormalizer) -> None:
    assert _gaiji_should_clauses("", normalizer) == []


def test_no_clauses_when_no_char_is_a_known_gaiji(
    normalizer: GaijiNormalizer,
) -> None:
    """A query of ordinary characters generates no should-clauses,
    so search behavior is identical to pre-1.3c2 — the safety property
    that keeps normal searches unaffected."""
    assert _gaiji_should_clauses("普通文本", normalizer) == []


def test_clauses_for_single_known_gaiji_glyph(normalizer: GaijiNormalizer) -> None:
    clauses = _gaiji_should_clauses("款", normalizer)
    assert _alternates_in(clauses) == {"[肄-聿+欠]", "U+F0001"}


def test_clauses_aggregate_across_multiple_gaiji_in_query(
    normalizer: GaijiNormalizer,
) -> None:
    """Multi-char queries expand each known glyph independently."""
    clauses = _gaiji_should_clauses("款穎", normalizer)
    assert _alternates_in(clauses) == {
        "[肄-聿+欠]",
        "U+F0001",
        "[(匕/示)*頁]",
        "U+F0002",
    }


def test_clauses_dedupe_repeated_glyphs(normalizer: GaijiNormalizer) -> None:
    """A character that appears twice in the query produces the
    alternates once, not twice."""
    clauses = _gaiji_should_clauses("款款款", normalizer)
    assert _alternates_in(clauses) == {"[肄-聿+欠]", "U+F0001"}


def test_clauses_mix_known_and_unknown_chars(normalizer: GaijiNormalizer) -> None:
    """Unknown chars are silently skipped — they contribute nothing
    to expansion and do not break the known-char path."""
    clauses = _gaiji_should_clauses("佛说款经", normalizer)
    assert _alternates_in(clauses) == {"[肄-聿+欠]", "U+F0001"}


def test_clauses_are_match_phrase_not_match(
    normalizer: GaijiNormalizer,
) -> None:
    """Composition like "[肄-聿+欠]" must be matched as a phrase —
    the cjk_content analyzer would otherwise tokenize the brackets
    away and the alternate wouldn't match the indexed bracket text."""
    clauses = _gaiji_should_clauses("款", normalizer)
    for c in clauses:
        assert "match_phrase" in c
        assert "match" not in c  # not the analyzed-match variant
