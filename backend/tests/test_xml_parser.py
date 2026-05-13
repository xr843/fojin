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


def test_paragraphs_still_extracted(tmp_path):
    """Regression guard: regular <p> text still works."""
    juans = parse_tei_xml(_write(tmp_path, PARAGRAPH_XML))
    assert len(juans) == 1
    content = juans[0]["content"]
    assert "如是我聞" in content
    assert "祇樹給孤獨園" in content
