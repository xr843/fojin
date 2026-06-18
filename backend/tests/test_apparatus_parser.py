"""Tests for CBETA critical apparatus (校勘异文) parsing.

CBETA uses standoff apparatus: the body carries <anchor xml:id="beg.../end..."/>
markers around a lemma, and <back><cb:div type="apparatus"> holds
<app from="#beg..." to="#end..."><lem wit="#wit.orig">底本字</lem>
<rdg resp="#resp2" wit="#wit1">校本字</rdg></app>.

The header declares witness sigla (<witness xml:id="wit1">【宋】</witness>) and
correctors (<respStmt xml:id="resp2"><name>Taisho</name></respStmt>).
"""

from app.core.xml_parser import parse_tei_apparatus, parse_tei_xml


def _write(tmp_path, xml: str):
    p = tmp_path / "t.xml"
    p.write_text(xml, encoding="utf-8")
    return p


# Faithful minimal CBETA TEI: header witnesses + respStmt, body anchors + <lb>,
# back apparatus. Two app entries: a substitution (辨→辯) and an omission.
APP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>x</title></titleStmt>
<publicationStmt><p>x</p></publicationStmt>
<sourceDesc><bibl>x</bibl></sourceDesc></fileDesc>
<encodingDesc><tagsDecl><namespace name="x"><tagUsage gi="x"><listWit>
<witness xml:id="wit.orig">【大】</witness>
<witness xml:id="wit1">【宋】</witness>
<witness xml:id="wit2">【元】</witness>
</listWit></tagUsage></namespace></tagsDecl></encodingDesc>
<revisionDesc>
<respStmt xml:id="resp1"><resp>corrections</resp><name>CBETA</name></respStmt>
<respStmt xml:id="resp2"><resp>corrections</resp><name>Taisho</name></respStmt>
</revisionDesc>
</teiHeader>
<text><body>
<milestone n="1" unit="juan"/>
<p><lb n="0001a01"/>如是我聞<anchor xml:id="beg0001004"/>辨<anchor xml:id="end0001004"/>之以法相。<anchor xml:id="beg0001009"/>長安<anchor xml:id="end0001009"/>釋之。</p>
</body>
<back>
<cb:div type="apparatus">
<head>校注</head>
<p>
<app from="#beg0001004" to="#end0001004"><lem wit="#wit.orig">辨</lem><rdg resp="#resp2" wit="#wit1 #wit2">辯</rdg></app>
<app from="#beg0001009" to="#end0001009"><lem wit="#wit.orig">長安</lem><rdg resp="#resp2" wit="#wit1"><space quantity="0"/></rdg></app>
</p>
</cb:div>
</back>
</text></TEI>
"""


def test_witnesses_mapped_to_sigla(tmp_path):
    """Header <witness xml:id> declarations resolve to readable sigla."""
    result = parse_tei_apparatus(_write(tmp_path, APP_XML))
    assert result["witnesses"]["wit.orig"] == "【大】"
    assert result["witnesses"]["wit1"] == "【宋】"
    assert result["witnesses"]["wit2"] == "【元】"


def test_anchor_offsets_recorded_and_content_clean(tmp_path):
    """parse_tei_xml records anchor char offsets without polluting content."""
    juans = parse_tei_xml(_write(tmp_path, APP_XML))
    juan = juans[0]
    # Content is the clean body text — no sentinels, no anchor artifacts.
    assert juan["content"] == "如是我聞辨之以法相。長安釋之。"
    assert not any(ord(c) < 0x20 and c != "\n" for c in juan["content"])
    # Anchors point at the right characters.
    a = juan["anchors"]
    assert juan["content"][a["beg0001004"]:a["end0001004"]] == "辨"
    assert juan["content"][a["beg0001009"]:a["end0001009"]] == "長安"


def test_line_anchors_recorded(tmp_path):
    """<lb n="..."/> page-col-line markers are captured with offsets (#2 prep)."""
    juans = parse_tei_xml(_write(tmp_path, APP_XML))
    lines = juans[0]["line_anchors"]
    assert {"offset": 0, "line": "0001a01"} in lines


def test_apparatus_entry_substitution(tmp_path):
    """A substitution app resolves lemma, sigla, readings, and offsets."""
    result = parse_tei_apparatus(_write(tmp_path, APP_XML))
    entry = next(e for e in result["entries"] if e["app_n"] == "0001004")
    assert entry["juan_num"] == 1
    assert entry["lemma"] == "辨"
    assert entry["lemma_siglum"] == "【大】"
    assert entry["aligned"] is True
    assert len(entry["readings"]) == 1
    rdg = entry["readings"][0]
    assert rdg["reading"] == "辯"
    assert rdg["witnesses"] == ["【宋】", "【元】"]
    assert rdg["resp"] == "Taisho"
    assert rdg["is_omission"] is False


def test_apparatus_offset_alignment_invariant(tmp_path):
    """Every aligned entry satisfies content[char_start:char_end] == lemma."""
    path = _write(tmp_path, APP_XML)
    juans = {j["juan_num"]: j["content"] for j in parse_tei_xml(path)}
    result = parse_tei_apparatus(path)
    for entry in result["entries"]:
        if entry["aligned"]:
            content = juans[entry["juan_num"]]
            assert content[entry["char_start"]:entry["char_end"]] == entry["lemma"]


# A lemma whose span crosses a line boundary: the parser joins lines with "\n",
# so content[start:end] contains a newline the lemma text does not. The offsets
# are still correct — alignment must ignore the interspersed newline.
LINEBREAK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader><fileDesc><titleStmt><title>x</title></titleStmt>
<publicationStmt><p>x</p></publicationStmt>
<sourceDesc><bibl>x</bibl></sourceDesc></fileDesc>
<encodingDesc><tagsDecl><namespace name="x"><tagUsage gi="x"><listWit>
<witness xml:id="wit.orig">【大】</witness>
<witness xml:id="wit1">【宋】</witness>
</listWit></tagUsage></namespace></tagsDecl></encodingDesc></teiHeader>
<text><body>
<milestone n="1" unit="juan"/>
<lg><l><anchor xml:id="beg1"/>拘</l><l>樓孫<anchor xml:id="end1"/>之</l></lg>
</body>
<back><cb:div type="apparatus"><head>校注</head><p>
<app from="#beg1" to="#end1"><lem wit="#wit.orig">拘樓孫</lem><rdg wit="#wit1">俱樓孫</rdg></app>
</p></cb:div></back>
</text></TEI>
"""


def test_apparatus_aligns_across_line_break(tmp_path):
    """A lemma spanning a line boundary still aligns (newline is ignored)."""
    result = parse_tei_apparatus(_write(tmp_path, LINEBREAK_XML))
    entry = next(e for e in result["entries"] if e["lemma"] == "拘樓孫")
    assert entry["aligned"] is True


def test_apparatus_omission_reading(tmp_path):
    """<rdg><space/></rdg> marks a witness that omits the lemma."""
    result = parse_tei_apparatus(_write(tmp_path, APP_XML))
    entry = next(e for e in result["entries"] if e["app_n"] == "0001009")
    assert entry["lemma"] == "長安"
    rdg = entry["readings"][0]
    assert rdg["is_omission"] is True
    assert rdg["reading"] == ""
    assert rdg["witnesses"] == ["【宋】"]
