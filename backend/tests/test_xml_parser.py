"""Tests for CBETA TEI XML parser, especially catalog-style texts."""

from app.core.xml_parser import parse_tei_xml


CATALOG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>Test catalog</title></titleStmt>
<publicationStmt><p>x</p></publicationStmt>
<sourceDesc><bibl>x</bibl></sourceDesc></fileDesc></teiHeader>
<text><body>
<milestone n="1" unit="juan"/>
<cb:div type="other">
<byline cb:type="author">延曆寺玄日大法師奉　聖王勅錄上</byline>
<list rend="no-marker">
<item><title>法華玄義十卷</title><note place="inline">天台智者大師說</note></item>
<item><title>法華玄義釋籤十卷</title><note place="inline">荊谿湛然大師述</note></item>
<item><title>法華玄義科文一卷</title><note place="inline">湛然述</note></item>
</list>
<p>百八十一部六百四十二卷。</p>
</cb:div>
</body></text></TEI>
"""


# Short sutra (T0251 心經) with a prepended imperial preface in a <cb:div type="xu">.
# The 御製序 sits BEFORE the <cb:juan>; the actual scripture is in <cb:div type="jing">.
# Old parser merged the preface into juan 1, burying the sutra body (觀自在…) and
# wrecking RAG recall for the most-cited sutra. The preface must be excluded.
PREFACE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>x</title></titleStmt>
<publicationStmt><p>x</p></publicationStmt>
<sourceDesc><bibl>x</bibl></sourceDesc></fileDesc></teiHeader>
<text><body>
<cb:div type="xu"><cb:mulu level="1" type="序">大明太祖高皇帝御製序</cb:mulu><head>大明太祖高皇帝御製般若心經序</head>
<p>二儀久判，萬物備周，子民者君君。</p>
<p>斯空相，前代帝王被所惑而幾喪天下者。</p>
</cb:div>
<cb:juan fun="open" n="001"><cb:jhead>般若波羅蜜多心經</cb:jhead></cb:juan>
<cb:div type="jing">
<p>觀自在菩薩行深般若波羅蜜多時，照見五蘊皆空，度一切苦厄。</p>
<p>色不異空，空不異色，色即是空，空即是色。</p>
</cb:div>
<cb:juan n="001" fun="close"/>
</body></text></TEI>
"""


PARAGRAPH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>x</title></titleStmt>
<publicationStmt><p>x</p></publicationStmt>
<sourceDesc><bibl>x</bibl></sourceDesc></fileDesc></teiHeader>
<text><body>
<milestone n="1" unit="juan"/>
<p>如是我聞。一時佛在舍衛國。</p>
<p>祇樹給孤獨園。與大比丘眾。</p>
</body></text></TEI>
"""


def _write(tmp_path, xml: str):
    p = tmp_path / "t.xml"
    p.write_text(xml, encoding="utf-8")
    return p


def test_catalog_items_are_extracted(tmp_path):
    """Catalog-style texts (T2178, X "科" series) use <list>/<item>/<title>.
    Parser must extract those titles, not just byline + trailing <p>.
    """
    juans = parse_tei_xml(_write(tmp_path, CATALOG_XML))
    assert len(juans) == 1
    content = juans[0]["content"]
    assert "法華玄義十卷" in content
    assert "法華玄義釋籤十卷" in content
    assert "法華玄義科文一卷" in content
    assert "延曆寺玄日大法師奉" in content  # byline still works
    assert "百八十一部六百四十二卷" in content  # trailing <p> still works
    # <note> inside <item> stays in SKIP_TAGS — the fix relies on this contract.
    assert "天台智者大師說" not in content
    assert "荊谿湛然大師述" not in content
    # Pre-fix: char_count was 32 (byline + trailing <p> only).
    # After fix: 3 titles add ~22 chars on top.
    assert juans[0]["char_count"] >= 48


def test_preface_xu_div_is_excluded(tmp_path):
    """Imperial/front-matter prefaces (<cb:div type="xu">) are paratext, not
    scripture. They must NOT be folded into the sutra body — otherwise a short
    sutra like 心經 (T0251) gets its 御製序 ranked as 'the text', and the real
    body never surfaces in retrieval.
    """
    juans = parse_tei_xml(_write(tmp_path, PREFACE_XML))
    assert len(juans) == 1
    content = juans[0]["content"]
    # Scripture body is kept …
    assert "觀自在菩薩行深般若波羅蜜多時" in content
    assert "色即是空" in content
    # … and the preface is gone.
    assert "御製" not in content
    assert "大明太祖" not in content
    assert "二儀久判" not in content
    # Body leads the content (no preface prefix burying it).
    assert content.lstrip().startswith("般若波羅蜜多心經") or content.lstrip().startswith("觀自在菩薩")


PREFACE_ONLY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>x</title></titleStmt>
<publicationStmt><p>x</p></publicationStmt>
<sourceDesc><bibl>x</bibl></sourceDesc></fileDesc></teiHeader>
<text><body>
<cb:div type="xu"><head>某經御製序</head>
<p>此序乃全文，別無正文。</p>
</cb:div>
</body></text></TEI>
"""


def test_preface_only_work_not_silently_emptied(tmp_path):
    """A work whose ONLY content is a <cb:div type="xu"> must still yield content.
    Returning [] would make import_work skip it silently (has_content stays
    False, nothing indexed). Fall back to the preface as juan 1.
    """
    juans = parse_tei_xml(_write(tmp_path, PREFACE_ONLY_XML))
    assert len(juans) == 1
    assert "此序乃全文" in juans[0]["content"]


def test_paragraphs_still_extracted(tmp_path):
    """Regression guard: regular <p> text still works."""
    juans = parse_tei_xml(_write(tmp_path, PARAGRAPH_XML))
    assert len(juans) == 1
    content = juans[0]["content"]
    assert "如是我聞" in content
    assert "祇樹給孤獨園" in content
