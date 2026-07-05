"""Unit tests for app.services.urn parse_urn + build_reader_url.

Resolution against the database is integration-shaped and lives in
test_urn_endpoint.py; the parser and URL builder are pure functions
and warrant their own focused coverage.
"""
from __future__ import annotations

import pytest

from app.services.urn import (
    ParsedURN,
    URNParseError,
    build_reader_url,
    build_urn,
    parse_urn,
)

# ──────────────────────────────────────────────────────────────────────
# parse_urn — happy path


def test_parse_text_level_urn() -> None:
    p = parse_urn("fojin:cbeta/T0001")
    assert p.scheme == "cbeta"
    assert p.work_id == "T0001"
    assert p.juan is None
    assert p.anchor is None


def test_parse_juan_level_urn() -> None:
    p = parse_urn("fojin:cbeta/T0001.5")
    assert p.work_id == "T0001"
    assert p.juan == 5
    assert p.anchor is None


def test_parse_line_level_urn() -> None:
    p = parse_urn("fojin:cbeta/T0001.5#p0001a01")
    assert p.juan == 5
    assert p.anchor == "p0001a01"


def test_parse_work_id_with_hyphen() -> None:
    """SC-mn10 / 84K-toh11 are real cbeta_id shapes."""
    p = parse_urn("fojin:cbeta/SC-mn10")
    assert p.work_id == "SC-mn10"

    q = parse_urn("fojin:cbeta/84K-toh11.2")
    assert q.work_id == "84K-toh11"
    assert q.juan == 2


@pytest.mark.parametrize("scheme", [
    "sc", "suttacentral", "84k", "kangyur", "gretil", "sa", "vri", "pali",
])
def test_parse_accepts_extended_schemes(scheme: str) -> None:
    """Scheme expansion (Wave 2.1 follow-up) — these were 422 before."""
    p = parse_urn(f"fojin:{scheme}/mn10")
    assert p.scheme == scheme
    assert p.work_id == "mn10"


def test_extended_scheme_with_juan_and_anchor() -> None:
    p = parse_urn("fojin:sc/mn10.2#segment-3")
    assert p.scheme == "sc"
    assert p.work_id == "mn10"
    assert p.juan == 2
    assert p.anchor == "segment-3"


# ──────────────────────────────────────────────────────────────────────
# parse_urn — error paths


def test_parse_rejects_empty() -> None:
    with pytest.raises(URNParseError):
        parse_urn("")


@pytest.mark.parametrize("urn", [
    "T0001",                            # no fojin: prefix
    "fojin:T0001",                      # no scheme/path slash
    "fojin:unknown/T0001",              # unknown scheme
    "fojin:cbeta/T0001.0",              # juan < 1
    "fojin:cbeta/T0001.abc",            # non-numeric juan
    "fojin:cbeta/../etc/passwd",        # path traversal attempt
    "fojin:cbeta/T0001#has spaces",     # invalid anchor char
])
def test_parse_rejects_malformed(urn: str) -> None:
    with pytest.raises(URNParseError):
        parse_urn(urn)


def test_parse_rejects_non_string() -> None:
    """The endpoint passes through whatever pydantic validates, but
    the parser itself should not crash on degenerate input."""
    with pytest.raises(URNParseError):
        parse_urn(None)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────
# build_reader_url


def _p(scheme: str, work: str, juan: int | None = None, anchor: str | None = None) -> ParsedURN:
    return ParsedURN(
        raw=f"fojin:{scheme}/{work}" + (f".{juan}" if juan else "") + (f"#{anchor}" if anchor else ""),
        scheme=scheme,
        work_id=work,
        juan=juan,
        anchor=anchor,
    )


def test_build_url_text_level_goes_to_detail_page() -> None:
    assert build_reader_url(_p("cbeta", "T0001"), text_id=42) == "/texts/42"


def test_build_url_juan_level_goes_to_reader() -> None:
    assert (
        build_reader_url(_p("cbeta", "T0001", juan=3), text_id=42)
        == "/reader?text=42&juan=3"
    )


def test_build_url_with_anchor_appends_anchor_param() -> None:
    assert (
        build_reader_url(_p("cbeta", "T0001", juan=3, anchor="p0001a01"), text_id=42)
        == "/reader?text=42&juan=3&anchor=p0001a01"
    )


def test_build_url_anchor_without_juan_is_dropped() -> None:
    """Pathological input — the parser rejects this, but defend the
    URL builder against degenerate ParsedURN literals."""
    p = _p("cbeta", "T0001", juan=None, anchor="p0001a01")
    assert build_reader_url(p, text_id=42) == "/texts/42"


# ──────────────────────────────────────────────────────────────────────
# Scheme → cbeta_id prefix expansion (Wave 2.1 follow-up)


def test_expand_work_id_cbeta_passthrough() -> None:
    """cbeta scheme is a no-op — the payload IS the cbeta_id."""
    from app.services.urn import _expand_work_id

    assert _expand_work_id(_p("cbeta", "T0001")) == "T0001"
    assert _expand_work_id(_p("cbeta", "X0123")) == "X0123"


@pytest.mark.parametrize("scheme,payload,expected_cbeta_id", [
    ("sc", "mn10", "SC-mn10"),
    ("suttacentral", "an1.1", "SC-an1.1"),
    ("84k", "11", "84K-toh11"),
    ("kangyur", "267", "84K-toh267"),
    ("gretil", "ramayana", "GRETIL-ramayana"),
    ("sa", "abhidh_k", "GRETIL-abhidh_k"),
    ("vri", "dn1", "VRI-dn1"),
    ("pali", "mn10", "VRI-mn10"),
])
def test_expand_work_id_applies_scheme_prefix(
    scheme: str, payload: str, expected_cbeta_id: str
) -> None:
    from app.services.urn import _expand_work_id

    # work_id_regex allows letters/digits/_/- — payloads like "an1.1"
    # contain '.' which the parser routes to juan. For the prefix
    # expansion unit test we bypass that and construct ParsedURN by hand.
    assert _expand_work_id(_p(scheme, payload)) == expected_cbeta_id


# ──────────────────────────────────────────────────────────────────────
# build_urn — forward builder (cbeta_id → URN), inverse of resolve_urn


@pytest.mark.parametrize("cbeta_id,expected", [
    ("T0001", "fojin:cbeta/T0001"),
    ("X0123", "fojin:cbeta/X0123"),
    ("SC-mn10", "fojin:sc/mn10"),
    ("84K-toh11", "fojin:84k/11"),
    ("GRETIL-ramayana", "fojin:gretil/ramayana"),
    ("VRI-dn1", "fojin:vri/dn1"),
])
def test_build_urn_emits_canonical_scheme(cbeta_id: str, expected: str) -> None:
    assert build_urn(cbeta_id) == expected


def test_build_urn_appends_juan_and_anchor() -> None:
    assert build_urn("T0001", 5) == "fojin:cbeta/T0001.5"
    assert build_urn("SC-mn10", 2) == "fojin:sc/mn10.2"
    assert build_urn("T0001", 5, "p0001a01") == "fojin:cbeta/T0001.5#p0001a01"


@pytest.mark.parametrize("cbeta_id,juan", [
    ("T0001", 3),
    ("X0123", None),
    ("SC-mn10", 1),
    ("84K-toh11", 2),
    ("GRETIL-ramayana", 7),
    ("VRI-dn1", None),
])
def test_build_urn_round_trips_through_parse_and_expand(
    cbeta_id: str, juan: int | None
) -> None:
    """build_urn → parse_urn → _expand_work_id must recover the original
    cbeta_id (and juan): the whole point of emitting only round-trippable URNs."""
    from app.services.urn import _expand_work_id

    urn = build_urn(cbeta_id, juan)
    assert urn is not None
    parsed = parse_urn(urn)
    assert _expand_work_id(parsed) == cbeta_id
    assert parsed.juan == juan


@pytest.mark.parametrize("cbeta_id", [None, "", "SC-", "SC-an1.1", "T 0001", "T0001."])
def test_build_urn_returns_none_when_not_round_trippable(cbeta_id) -> None:
    """Missing id, empty work payload, or a work_id carrying '.'/space that the
    parser would reject → None, never a malformed reference or an exception."""
    assert build_urn(cbeta_id) is None


def test_build_urn_drops_invalid_anchor_but_keeps_urn() -> None:
    """A bad anchor must not sink an otherwise-valid citation id."""
    assert build_urn("T0001", 5, "has spaces") == "fojin:cbeta/T0001.5"


def test_build_urn_ignores_non_positive_juan() -> None:
    assert build_urn("T0001", 0) == "fojin:cbeta/T0001"
