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


# 真实 CBETA 的写法：段首那一行的 <lb> 在 <p> / <head> / <byline> 外面（T09n0278 原样节选）。
LB_OUTSIDE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0">
<teiHeader/>
<text><body>
<lb n="0395a01" ed="T"/>
<lb n="0395a03" ed="T"/><cb:juan n="001" fun="open"><cb:jhead><title>大方廣佛華嚴經</title>卷第一</cb:jhead></cb:juan>
<lb n="0395a05" ed="T"/><byline>東晉天竺三藏佛馱跋陀羅譯</byline>
<lb n="0395a06" ed="T"/><cb:div type="pin"><head>世間淨眼品第一</head>
<lb n="0395a07" ed="T"/><p>如是我聞：</p><p cb:place="inline">一時，佛在摩竭提國寂滅道場始
<lb n="0395a08" ed="T"/>成正覺。</p>
<lb n="0395b11" ed="T"/><p>與十佛世界微塵數等大菩薩俱，其名曰：普
<lb n="0395b12" ed="T"/>賢菩薩、普德智光菩薩。</p>
</cb:div>
</body></text></TEI>
"""


def _ref_at(juan: dict, needle: str) -> str:
    """选区起点落在 needle 首字时，前端取「之前最近的行号」——这里照同一规则算。"""
    pos = juan["content"].index(needle)
    return [la["line"] for la in juan["line_anchors"] if la["offset"] <= pos][-1]


def test_line_anchor_outside_paragraph_is_kept(tmp_path):
    """段首行的 <lb> 在 <p> 外面：原先整条丢失，段首行的字被算到上一段末行。"""
    juan = parse_tei_xml(_write(tmp_path, LB_OUTSIDE_XML))[0]
    assert _ref_at(juan, "如是我聞") == "0395a07"
    assert _ref_at(juan, "成正覺") == "0395a08"
    assert _ref_at(juan, "與十佛") == "0395b11"  # 修前是 0395a08
    assert _ref_at(juan, "普\n賢") == "0395b11"
    assert _ref_at(juan, "賢菩薩") == "0395b12"
    assert _ref_at(juan, "世間淨眼品") == "0395a06"
    assert _ref_at(juan, "東晉") == "0395a05"
    assert _ref_at(juan, "大方廣佛華嚴經") == "0395a03"
    # 卷首空行 a01 没有字，不单独占一个锚点
    assert "0395a01" not in {la["line"] for la in juan["line_anchors"]}


def test_line_anchor_outside_paragraph_ignores_r_edition(tmp_path):
    """卍续藏段外并列的 R 版 <lb> 编号会和本藏撞车，不能拿来当行号（X0288 原样节选）。"""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0"><teiHeader/><text><body>
<lb ed="X" n="0002c18"/><lb ed="R022" n="0005a10"/><p>閱正</p>
<lb ed="X" n="0005a10"/><lb ed="R022" n="0008a02"/><p>寔無可讚</p>
</body></text></TEI>
"""
    juan = parse_tei_xml(_write(tmp_path, xml))[0]
    assert _ref_at(juan, "閱正") == "0002c18"
    assert _ref_at(juan, "寔無可讚") == "0005a10"
    assert {la["line"] for la in juan["line_anchors"]} == {"0002c18", "0005a10"}


def test_line_anchor_outside_paragraph_ignores_old_type(tmp_path):
    """印順著作集段外并列 type="old" 的旧版 <lb>，同样不能当行号（Y13n0013 原样节选）。"""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0"><teiHeader/><text><body>
<lb n="0002a04" ed="Y"/><lb n="0002a05" ed="Y" type="old"/><p>唯心，為大師出家之法名
<lb n="0002a05" ed="Y"/><lb n="0002a06" ed="Y" type="old"/>覺昌隆</p>
</body></text></TEI>
"""
    juan = parse_tei_xml(_write(tmp_path, xml))[0]
    assert _ref_at(juan, "唯心") == "0002a04"


def test_line_anchor_outside_paragraph_leaves_content_unchanged(tmp_path):
    """只多记行号，正文一个字不变（校勘偏移依赖正文，不能动）。"""
    juan = parse_tei_xml(_write(tmp_path, LB_OUTSIDE_XML))[0]
    assert not any(ord(c) < 0x20 and c != "\n" for c in juan["content"])
    assert juan["content"].startswith("大方廣佛華嚴經卷第一\n東晉天竺三藏佛馱跋陀羅譯\n世間淨眼品第一\n\n如是我聞：")


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


GAIJI_RDG_XML = """<?xml version="1.0" encoding="UTF-8"?>
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
<p><anchor xml:id="beg1"/>慧<anchor xml:id="end1"/>命。</p>
</body>
<back><cb:div type="apparatus"><head>校注</head><p>
<app from="#beg1" to="#end1"><lem wit="#wit.orig">慧</lem><rdg wit="#wit1">大<g ref="#CB99999">慧</g></rdg></app>
</p></cb:div></back>
</text></TEI>
"""


def test_apparatus_reading_resolves_gaiji(tmp_path):
    """A <g> gaiji inside a <rdg> is resolved (here via the non-PUA text fallback)."""
    result = parse_tei_apparatus(_write(tmp_path, GAIJI_RDG_XML))
    entry = next(e for e in result["entries"] if e["lemma"] == "慧")
    assert entry["readings"][0]["reading"] == "大慧"


def test_apparatus_omission_reading(tmp_path):
    """<rdg><space/></rdg> marks a witness that omits the lemma."""
    result = parse_tei_apparatus(_write(tmp_path, APP_XML))
    entry = next(e for e in result["entries"] if e["app_n"] == "0001009")
    assert entry["lemma"] == "長安"
    rdg = entry["readings"][0]
    assert rdg["is_omission"] is True
    assert rdg["reading"] == ""
    assert rdg["witnesses"] == ["【宋】"]
