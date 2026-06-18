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
