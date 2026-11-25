"""问答「相关词条」卡片的取词与摘要（services/dictionary_related.py）。"""

from app.services.dictionary_related import CARD_SOURCES, extract_terms, make_excerpt


def test_extract_terms_strips_question_words():
    assert extract_terms("什么是三藏") == ["三藏"]
    assert extract_terms("流转门 还灭门怎么理解") == ["流转门", "还灭门"]


def test_extract_terms_drops_generic_words_in_both_scripts():
    # 「什么」「但是」「修行」在辞典里有条目，但做成卡片没有信息量（2026-11-25 试跑实测）
    assert extract_terms("但是 修行 俱有依") == ["俱有依"]
    assert extract_terms("翻譯 世尊 等無間緣") == ["等無間緣"]


def test_extract_terms_dedupes_and_caps():
    terms = extract_terms("三藏 三藏 甲乙 丙丁 戊己 庚辛 壬癸 子丑 寅卯")
    assert terms[0] == "三藏" and terms.count("三藏") == 1
    assert len(terms) <= 6


def test_make_excerpt_strips_repeated_headword_and_rejects_empty_entries():
    # 中華佛教百科首行就是词头；去掉后没有释义的条目不出卡片
    assert make_excerpt("十住心論", "十住心論") is None
    assert make_excerpt("長行", "長行\n\n謂經文中，直宣說法相，而不限定字句之文句。") == "謂經文中，直宣說法相，而不限定字句之文句。"
    assert make_excerpt("作意", "見某條。") is None


def test_make_excerpt_truncates_long_definitions():
    text = "甲" * 200
    out = make_excerpt("乙", text)
    assert out is not None and out.endswith("…") and len(out) == 91


def test_card_sources_exclude_foreign_and_phonetic_dictionaries():
    # 英文短释义、音义书（反切）、经录不做卡片
    for code in ("nti-reader", "dila-soothill", "bs-suihan-lu", "bs-yiqiejing-yinyi", "yuezang-zhijin", "cdsl-mw"):
        assert code not in CARD_SOURCES
    assert CARD_SOURCES[0] == "foguang"
