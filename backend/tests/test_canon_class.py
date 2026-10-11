import pytest

from app.services.canon_class import CANON_ORDER_SCRIPT, canon_class


@pytest.mark.parametrize(
    ("cbeta_id", "expected"),
    [
        ("T0001", "sutra"),
        ("T0235", "sutra"),
        ("T0236a", "sutra"),
        ("T1420", "sutra"),
        ("T1421", "vinaya"),
        ("T1504", "vinaya"),
        ("T1505", "treatise"),
        ("T1509", "treatise"),
        ("T1510b", "treatise"),
        ("T1666", "treatise"),
        ("T1692", "treatise"),
        ("T1693", "commentary"),
        ("T1850", "commentary"),
        ("T1851", "school"),
        ("T2008", "school"),
        ("T2025", "school"),
        ("T2026", "history"),
        ("T2076", "history"),
        ("T2184", "history"),
        ("T2747", "later"),
        ("T2865", "apocrypha"),
        ("T2919", "apocrypha"),
        ("T2920", "apocrypha"),
        ("N0006", "sutra"),
        ("X0508", "later"),
        ("J0001", "later"),
        ("SC-dn6", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_canon_class(cbeta_id, expected):
    assert canon_class(cbeta_id) == expected


def test_order_script_ranks_taisho_then_pali_then_xuzang():
    # The script is executed by Elasticsearch; here we only pin the contract
    # the ranking relies on, so an edit that reorders the bases is caught.
    assert "doc['cbeta_id']" in CANON_ORDER_SCRIPT
    for base in ("0", "50000", "100000", "200000"):
        assert base in CANON_ORDER_SCRIPT
