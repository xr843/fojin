"""Taishō → Goryeo (KABC) cross-reference mapping tests."""

from app.services.goryeo import goryeo_k, kabc_url


def test_known_taisho_maps_to_goryeo_k():
    # T1579 瑜伽師地論 → K0570 (Lancaster catalogue / acmuller Taishō index).
    assert goryeo_k("T1579") == "K0570"
    assert goryeo_k("T0001") == "K0647"
    assert goryeo_k("T0251") == "K0020"


def test_kabc_url_built_from_k_number():
    assert kabc_url("T1579") == "https://kabc.dongguk.edu/content/view?dataId=ABC_IT_K0570"


def test_no_goryeo_parallel_returns_none():
    # Xuzangjing has no Goryeo parallel; unknown ids too.
    assert goryeo_k("X0001") is None
    assert goryeo_k("T9999") is None
    assert kabc_url("X0001") is None


def test_witness_variant_falls_back_to_base_work():
    # Bug 2026-06-23: a letter suffix marks a different 见证/edition of the SAME
    # work (T0235b = a witness of 鸠摩罗什 金刚经). These weren't in the map, so the
    # reader's 高丽藏 button silently vanished. Fall back to the base work's K.
    assert goryeo_k("T0235b") == "K0013"
    assert goryeo_k("T0236a") == "K0014"  # 麗本/宋本 of 菩提流支 金刚经 → that work
    assert goryeo_k("T0236b") == "K0014"
    assert kabc_url("T0235b") == "https://kabc.dongguk.edu/content/view?dataId=ABC_IT_K0013"


def test_explicitly_mapped_suffix_variants_keep_their_own_K():
    # SAFETY: T0150a/b are SEPARATELY mapped to DISTINCT K-numbers — exact match
    # must win so the fallback never collapses them to a shared (unmapped) base.
    assert goryeo_k("T0150a") == "K0738"
    assert goryeo_k("T0150b") == "K0882"
    assert goryeo_k("T0150") is None  # base genuinely unmapped (splits into a/b)


def test_empty_and_none_return_none():
    assert goryeo_k("") is None
    assert goryeo_k(None) is None
