"""迁移 0188：只合成「拉丁字母＋组合附加符号」，其他字一概不动。

尤其是 CJK 兼容表意字（U+F900–U+FAFF）：整串 NFC 会把它们并成统一表意字，而音義類
辭典（可洪、慧琳）和 NTI 正是用这些码位区分異體——生产里 226 行有这种字。
"""

import importlib.util
import unicodedata
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0188_nfc_latin_diacritics_in_dictionary_20261108.py"
_spec = importlib.util.spec_from_file_location("m0188", _PATH)
m0188 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m0188)
compose = m0188.compose_latin


def test_decomposed_iast_is_composed():
    decomposed = "ru\u0304pam\u0323 s\u0301u\u0304nyata\u0304"
    assert compose(decomposed) == "rūpaṃ śūnyatā"
    assert compose(decomposed) == unicodedata.normalize("NFC", decomposed)


def test_cjk_compatibility_ideographs_are_left_alone():
    s = "\uF900\uFA0E 可洪音義 u\u0304"
    out = compose(s)
    assert out.startswith("\uF900\uFA0E")  # 整串 NFC 会把它们换掉
    assert unicodedata.normalize("NFC", s) != s
    assert out.endswith("ū")


def test_devanagari_and_plain_text_untouched():
    s = "क\u093C ड\u093C 已是預組合的 ū ā"  # Devanagari + nukta：NFC 会改，但不在本迁移范围
    assert compose(s) == s


def test_mark_without_precomposed_form_stays_as_is():
    s = "m\u0310"  # m + candrabindu：Unicode 没有预组合字
    assert compose(s) == s
