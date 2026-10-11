"""The live text_contents analysis was built by a standalone ops script; the
app's CONTENT_INDEX_SETTINGS must define the same filters, or the next index
rebuild from code silently brings back the hard-wrap phrase misses."""

import importlib.util
from pathlib import Path

from app.core.elasticsearch import CONTENT_INDEX_SETTINGS

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "es_text_contents_join_wraps.py"


def _script_module(monkeypatch):
    for k, v in {"ES_HOST": "http://es:9200", "ES_USER": "u", "ES_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("es_join_wraps", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_code_and_ops_script_define_the_same_char_filters(monkeypatch):
    mod = _script_module(monkeypatch)
    cf = CONTENT_INDEX_SETTINGS["settings"]["analysis"]["char_filter"]
    assert cf["cbeta_join_han_wraps"] == mod.HAN_WRAP_CHAR_FILTER
    assert cf["cbeta_strip_han_punct"] == mod.HAN_PUNCT_CHAR_FILTER


def test_content_field_carries_the_nopunct_subfield():
    analysis = CONTENT_INDEX_SETTINGS["settings"]["analysis"]["analyzer"]
    assert analysis["cjk_content"]["char_filter"] == ["cbeta_join_han_wraps"]
    assert analysis["cjk_nopunct"]["char_filter"] == ["cbeta_strip_han_punct"]
    content = CONTENT_INDEX_SETTINGS["mappings"]["properties"]["content"]
    assert content["fields"]["nopunct"]["analyzer"] == "cjk_nopunct"
