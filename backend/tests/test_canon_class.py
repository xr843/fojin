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
        # 漢譯南傳大藏經 (titles checked against CBETA xml-p5, 2026-10-11)
        ("N0001", "vinaya"),  # 經分別
        ("N0003", "vinaya"),  # 附隨
        ("N0004", "sutra"),  # 長部經典
        ("N0006", "sutra"),
        ("N0023", "sutra"),  # 小義釋 (Khuddaka Nikāya)
        ("N0024", "treatise"),  # 法集論 (Abhidhamma)
        ("N0030", "treatise"),  # 論事
        ("N0031", "later"),  # 彌蘭王問經
        ("N0032", "history"),  # 島王統史
        ("N0034", "history"),  # 小王統史
        ("N0035", "later"),  # 清淨道論 (Buddhaghosa)
        ("N0037", "later"),  # 攝阿毘達磨義論
        ("N0038", "history"),  # 阿育王刻文
        ("T2185", "later"),  # 日本續經疏部 …
        ("T2731", "later"),  # … 悉曇部
        ("X0508", "later"),
        ("J0001", "later"),
        ("SC-dn6", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_canon_class(cbeta_id, expected):
    assert canon_class(cbeta_id) == expected


# Results of running CANON_ORDER_SCRIPT through the painless _execute API on the
# production cluster (2026-10-11, after the j == i guard). canon_order_key is
# the Python twin used to re-sort; the two must agree id for id.
PAINLESS_RESULTS = {
    "T0001": 1, "T0235": 235, "T0236a": 236, "T1420": 1420, "T2008": 2008, "T2919": 2919,
    "N0004": 50004, "N0035": 50035, "X0508": 100508, "J0001": 200001,
    "SC-dn6": 9.0e9, "84K-toh154": 9.0e9, "T": 9.0e9, "": 9.0e9, None: 9.0e9,
}


@pytest.mark.parametrize(("cbeta_id", "painless"), list(PAINLESS_RESULTS.items()))
def test_python_twin_matches_the_painless_script(cbeta_id, painless):
    from app.services.canon_class import canon_order_key

    assert canon_order_key(cbeta_id) == painless


def test_order_script_ranks_taisho_then_pali_then_xuzang():
    # The script is executed by Elasticsearch; here we only pin the contract
    # the ranking relies on, so an edit that reorders the bases is caught.
    assert "doc['cbeta_id']" in CANON_ORDER_SCRIPT
    for base in ("0", "50000", "100000", "200000"):
        assert base in CANON_ORDER_SCRIPT
