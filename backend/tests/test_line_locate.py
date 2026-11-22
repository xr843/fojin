"""Line-level links for verified quotes: find where in the fascicle a quote
sits, then the CBETA line it starts on (user feedback 2026-11-22: 「点击查看原文
后，如果能直接定位到所查的那句，就方便啦」)."""

from app.services.line_locate import locate_offset, nearest_line

CONTENT = "從此第三，明忍智次第。\n釋曰：忍是無間道，約斷惑得，不被惑得之所隔礙，故名無間。智是解脫道。"


def test_simplified_quote_maps_back_to_its_offset_in_the_traditional_text():
    at = locate_offset(CONTENT, "忍是无间道，约断惑得，不被惑得之所隔碍，故名无间。")
    assert at is not None
    assert CONTENT[at:].startswith("忍是無間道")


def test_punctuation_and_line_breaks_do_not_matter():
    assert locate_offset("如夢、幻、\n泡、影", "如梦幻泡影") == 0


def test_variant_spellings_fold_like_the_verifier():
    at = locate_offset("觀自在菩薩。心無罣礙，無罣礙故", "心无挂碍，无挂碍故")
    assert at == 6


def test_absent_quote_has_no_offset():
    assert locate_offset(CONTENT, "一切都是最好的安排") is None


def test_nearest_line_is_the_last_marker_at_or_before_the_offset():
    anchors = [(0, "0947a14"), (11, "0947a15"), (20, "0947a16")]
    assert nearest_line(anchors, 0) == "0947a14"
    assert nearest_line(anchors, 19) == "0947a15"
    assert nearest_line(anchors, 20) == "0947a16"
    assert nearest_line([], 5) is None
