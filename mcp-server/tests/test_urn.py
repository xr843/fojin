"""Round-trip + degradation tests for the vendored URN builder.

Must stay behaviourally identical to backend/app/services/urn.py::build_urn —
these cases mirror backend/tests/test_urn.py's build_urn coverage.
"""

import pytest

from fojin_mcp.urn import build_urn


@pytest.mark.parametrize("cbeta_id,expected", [
    ("T0001", "fojin:cbeta/T0001"),
    ("X0123", "fojin:cbeta/X0123"),
    ("SC-mn10", "fojin:sc/mn10"),
    ("84K-toh11", "fojin:84k/11"),
    ("GRETIL-ramayana", "fojin:gretil/ramayana"),
    ("VRI-dn1", "fojin:vri/dn1"),
])
def test_emits_canonical_scheme(cbeta_id, expected):
    assert build_urn(cbeta_id) == expected


def test_appends_juan_and_anchor():
    assert build_urn("T0001", 5) == "fojin:cbeta/T0001.5"
    assert build_urn("SC-mn10", 2) == "fojin:sc/mn10.2"
    assert build_urn("T0001", 5, "p0001a01") == "fojin:cbeta/T0001.5#p0001a01"


@pytest.mark.parametrize("cbeta_id", [None, "", "SC-", "SC-an1.1", "T 0001", "T0001.", 123])
def test_returns_none_when_not_round_trippable(cbeta_id):
    assert build_urn(cbeta_id) is None


def test_drops_bad_anchor_keeps_urn():
    assert build_urn("T0001", 5, "has spaces") == "fojin:cbeta/T0001.5"


def test_ignores_non_positive_juan():
    assert build_urn("T0001", 0) == "fojin:cbeta/T0001"
    assert build_urn("T0001", None) == "fojin:cbeta/T0001"
