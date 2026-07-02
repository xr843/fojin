"""Pure-logic tests for the term-concept builder + IAST normalizer.

No DB / LLM / network. These pin the parsing the whole cross-lingual layer
depends on (the full build runs against the prod corpus DB, not CI). Samples are
verbatim from the live corpus (翻譯名義大集 / 四譯合璧輯要 entries for 涅槃).
"""

from scripts.build_term_concepts import (
    classify_script,
    parse_mvp_entry,
    parse_siyi_definition,
)

from app.services.term_concept_service import normalize_iast

# --- normalize_iast --------------------------------------------------------


def test_normalize_folds_diacritics_and_case():
    assert normalize_iast("nirvāṇa") == "nirvana"


def test_normalize_drops_accusative_m_so_citation_forms_collapse():
    # Mahāvyutpatti cites "nirvāṇam"; MW headword is "nirvāṇa" — both must match.
    assert normalize_iast("nirvāṇam") == normalize_iast("nirvāṇa") == "nirvana"


def test_normalize_pali_stays_distinct_from_sanskrit():
    # Documents the Phase-1 Pali boundary: nibbāna does NOT fold to nirvana.
    assert normalize_iast("nibbāna") == "nibbana"
    assert normalize_iast("nibbāna") != normalize_iast("nirvāṇa")


def test_normalize_takes_first_line_only():
    assert normalize_iast("nirvāṇam\n            निर्वाणम्") == "nirvana"


def test_normalize_shared_form_matches():
    assert normalize_iast("bodhi") == normalize_iast("Bodhi") == "bodhi"


def test_normalize_empty_and_non_latin():
    assert normalize_iast("") == ""
    assert normalize_iast(None) == ""
    assert normalize_iast("涅槃") == ""


# --- classify_script -------------------------------------------------------


def test_classify_script_by_block():
    assert classify_script("nirvāṇam") == "latin"
    assert classify_script("निर्वाणम्") == "devanagari"
    assert classify_script("涅槃") == "han"
    assert classify_script("མྱ་ངན་ལས་འདས་པ་") == "tibetan"


def test_classify_script_skips_leading_punctuation_whitespace():
    assert classify_script("   涅槃") == "han"
    assert classify_script("'das pa") == "latin"  # Wylie apostrophe then latin


def test_classify_script_empty_is_other():
    assert classify_script("") == "other"
    assert classify_script("。、") == "other"


# --- parse_mvp_entry (Mahāvyutpatti) ---------------------------------------

# Verbatim shape of corpus entry mvp-1714 (nirvāṇam).
MVP_HEADWORD = "nirvāṇam\n            निर्वाणम्"
MVP_DEF = (
    "nirvāṇam\n            निर्वाणम्\n          \n          \n"
    "            涅槃\n          \n          \n            清淨涅槃\n          \n          \n"
    "            mya ngan las 'das pa\n          \n          \n            མྱ་ངན་ལས་འདས་པ་"
)


def test_parse_mvp_extracts_all_languages():
    p = parse_mvp_entry(MVP_HEADWORD, MVP_DEF)
    assert p["sanskrit"] == "nirvāṇam"
    assert p["devanagari"] == "निर्वाणम्"
    assert p["chinese"] == ["涅槃", "清淨涅槃"]  # order preserved, deduped
    assert p["tibetan"] == "མྱ་ངན་ལས་འདས་པ་"  # Unicode script, not the Wylie line


def test_parse_mvp_handles_missing_fields():
    p = parse_mvp_entry("bodhi", "bodhi\n          菩提")
    assert p["sanskrit"] == "bodhi"
    assert p["chinese"] == ["菩提"]
    assert p["tibetan"] is None
    assert p["devanagari"] is None


def test_parse_mvp_empty():
    p = parse_mvp_entry(None, None)
    assert p == {"sanskrit": None, "devanagari": None, "chinese": [], "tibetan": None}


# --- parse_siyi_definition (四譯合璧輯要) -----------------------------------

# Verbatim shape of corpus entry siyi-hebi-nirvāṇam.
SIYI_DEF = (
    "nirvāṇam\n【梵】nirvāṇam\n【滿】gasacun ci duleke\n"
    "【蒙】gasalang asa nögchikhsen\n【漢】涅槃"
)


def test_parse_siyi_extracts_core_four_languages():
    p = parse_siyi_definition(SIYI_DEF)
    assert p["sanskrit"] == "nirvāṇam"
    assert p["chinese"] == "涅槃"
    # Manchu / Mongolian tags are present but intentionally dropped in Phase 1.
    assert "manchu" not in p
    assert "mongolian" not in p


def test_parse_siyi_partial_tags():
    p = parse_siyi_definition("【梵】bodhi\n【漢】菩提\n【藏】byang chub")
    assert p == {"sanskrit": "bodhi", "chinese": "菩提", "tibetan": "byang chub"}


def test_parse_siyi_empty():
    assert parse_siyi_definition("") == {}
    assert parse_siyi_definition(None) == {}
