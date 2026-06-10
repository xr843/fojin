"""Unit tests for canon (底本) derivation in app.services.text.

The runtime helper must stay in lockstep with the offline equivalent
in scripts/build_works.py — when adding a prefix here, sync there
too, and vice versa.
"""
from __future__ import annotations

import pytest

from app.services.text import canon_from_cbeta_id, canon_label_zh


@pytest.mark.parametrize(
    "cbeta_id,expected_code,expected_label",
    [
        ("T0251", "taisho", "大正藏"),
        ("T1579", "taisho", "大正藏"),
        ("X0123", "xuzang", "卍续藏"),
        ("SC-mn10", "pali", "巴利三藏"),
        ("VRI-an1", "pali", "巴利三藏"),
        ("84K-toh11", "kangyur", "甘珠尔"),
        ("GRETIL-rama", "gretil", "梵文 GRETIL"),
    ],
)
def test_canon_from_known_prefix(
    cbeta_id: str, expected_code: str, expected_label: str
) -> None:
    code = canon_from_cbeta_id(cbeta_id)
    assert code == expected_code
    assert canon_label_zh(code) == expected_label


@pytest.mark.parametrize("cbeta_id", [None, "", "UNKNOWN-001", "FOO0001"])
def test_canon_unknown_prefix_returns_none(cbeta_id: str | None) -> None:
    code = canon_from_cbeta_id(cbeta_id)
    assert code is None
    assert canon_label_zh(code) is None


def test_canon_label_for_unknown_code_returns_none() -> None:
    """An out-of-vocabulary code (e.g. canon='other') yields no label
    rather than raising — schema returns canon=None on bad data."""
    assert canon_label_zh("other") is None
    assert canon_label_zh(None) is None
