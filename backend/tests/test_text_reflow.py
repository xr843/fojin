"""Reflow tests — port of the frontend reflowText heuristic.

These pin the segment classification (prose merge, verse, structural lines)
so the exported HTML/EPUB/DOCX matches the web reader's layout.
"""

from app.services.text_reflow import Segment, reflow


def _types(segs: list[Segment]) -> list[str]:
    return [s.type for s in segs]


def test_prose_lines_merge_into_one_paragraph():
    # CBETA hard-wraps prose every ~18 chars; reflow rejoins into flowing paras.
    raw = "聖眾，故先讚德方申敬禮。諸言所表謂佛\n世尊具眾德故，故先讚歎然後歸禮。"
    segs = reflow(raw)
    prose = [s for s in segs if s.type == "prose"]
    assert len(prose) == 1
    assert prose[0].text == "聖眾，故先讚德方申敬禮。諸言所表謂佛世尊具眾德故，故先讚歎然後歸禮。"


def test_blank_line_breaks_paragraph_only_after_sentence_end():
    # Break only when the previous line ends with sentence-final punctuation.
    # Use multi-clause prose lines (3+ puncts) so they aren't caught as verse.
    raw = "聖眾，故先讚德方申敬禮，具眾德故。\n\n諸言所表，謂佛世尊，具眾德故。"
    segs = reflow(raw)
    assert _types(segs) == ["prose", "break", "prose"]

    # Mid-word blank (no sentence-final punct) must NOT break.
    raw2 = "淨\n\n色相海。"
    segs2 = reflow(raw2)
    assert [s.type for s in segs2] == ["prose"]
    assert segs2[0].text == "淨色相海。"


def test_juan_byline_section_head_are_structural():
    raw = (
        "大方廣佛華嚴經\n"
        "大方廣佛華嚴經卷第一\n"
        "于闐國三藏實叉難陀奉　制譯\n"
        "世主妙嚴品第一之一\n"
        "爾時世尊，處於此座，於一切法成最正覺。"
    )
    segs = reflow(raw)
    by_type = {s.type: s.text for s in segs}
    assert by_type["head"] == "大方廣佛華嚴經"
    assert by_type["juan"] == "大方廣佛華嚴經卷第一"
    assert by_type["byline"] == "于闐國三藏實叉難陀奉　制譯"
    assert by_type["section"] == "世主妙嚴品第一之一"
    assert by_type["prose"] == "爾時世尊，處於此座，於一切法成最正覺。"


def test_opening_verse_detected_before_first_prose():
    # Equal-length clause lines before any 論曰 are opening verses.
    raw = "諸一切種諸冥滅，\n拔眾生出生死泥，"
    segs = reflow(raw)
    assert _types(segs) == ["verse", "verse"]


def test_verse_block_after_marker_then_prose_exits():
    raw = "頌曰：\n身從無相中受生，\n猶如幻出諸形相。\n論曰：如是等義。"
    segs = reflow(raw)
    types = _types(segs)
    assert "verse" in types
    # the 論曰 line is prose, not verse
    assert segs[-1].type == "prose"
    assert segs[-1].text.startswith("論曰")


def test_empty_input_yields_no_segments():
    assert reflow("") == []
    assert reflow("\n\n") == []


def test_juan_digit_class_is_ascii_only_like_js():
    # JS RegExp \d matches ASCII digits only; Python's Unicode \d also matches
    # fullwidth digits. We pin ASCII-only so the export mirrors the web reader.
    # ASCII digit juan → recognised
    assert reflow("大方廣佛華嚴經卷第1")[0].type == "juan"
    # Fullwidth-digit juan → NOT a juan (matches JS), falls through to prose
    assert reflow("大方廣佛華嚴經卷第１")[0].type != "juan"
